#!/usr/bin/env python3
"""
analyze_latency.py
------------------
Runs latency analysis for all proxy strategies and generates comparison plots.
Tests sjf, fair, and fcfs strategies with Customer A (short bursts) and Customer B (large blocks).
"""

import asyncio
import random
import time
import httpx
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from typing import List, Dict, Tuple
import os
import requests

PROXY = "http://localhost:8000/proxy_classify"
STRATEGY_URL = "http://localhost:8000/strategy"
RESULTS_DIR = "results"

# Test configuration
TEST_DURATION = 30  # seconds per strategy
STRATEGIES = ["sjf", "fair", "fcfs"]

class LatencyCollector:
    def __init__(self):
        self.customer_a_data = []
        self.customer_b_data = []
        self.start_time = time.time()
    
    def add_customer_a(self, latency_ms: float, proxy_latency_ms: int):
        self.customer_a_data.append({
            'timestamp': time.time() - self.start_time,
            'total_latency': latency_ms,
            'proxy_latency': proxy_latency_ms
        })
    
    def add_customer_b(self, latency_ms: float, proxy_latency_ms: int):
        self.customer_b_data.append({
            'timestamp': time.time() - self.start_time,
            'total_latency': latency_ms,
            'proxy_latency': proxy_latency_ms
        })

def _random_code():
    return "def foo(): pass" if random.random() < 0.5 else "hello world"

async def customer_a(cli: httpx.AsyncClient, collector: LatencyCollector, duration: float):
    """Customer A: High-frequency short requests - 3 requests per second with 1-3 sequences each"""
    end_time = time.time() + duration
    
    while time.time() < end_time:
        # Vary the number of sequences to create different sized requests
        num_sequences = random.randint(1, 3)
        snippets = [_random_code()[:random.randint(5, 15)] for _ in range(num_sequences)]
        
        t0 = time.time()
        try:
            r = await cli.post(PROXY, json={"sequences": snippets},
                             headers={"X-Customer-Id": "A"}, timeout=10)
            if r.status_code == 200:
                lat = (time.time() - t0) * 1_000
                data = r.json()
                collector.add_customer_a(lat, data['proxy_latency_ms'])
                print(f"A: {num_sequences} seqs done in {lat:6.1f} ms "
                      f"(proxy said {data['proxy_latency_ms']} ms)")
            else:
                print(f"A: Error {r.status_code}: {r.text}")
        except Exception as e:
            print(f"A: Exception: {e}")
        
        # High frequency - approximately 3 requests per second
        await asyncio.sleep(0.33)

async def customer_b(cli: httpx.AsyncClient, collector: LatencyCollector, duration: float):
    """Customer B: Medium-frequency larger requests - 1.5 requests per second with 2-5 sequences each"""
    end_time = time.time() + duration
    
    while time.time() < end_time:
        # Larger requests with more sequences
        num_sequences = random.randint(2, 5)
        snippets = []
        for _ in range(num_sequences):
            if random.random() < 0.3:  # 30% chance of very large sequence
                snippet = "class LargeClass:\n" + ("    def method(self): pass\n" * 20)
            else:  # 70% chance of medium sequence
                snippet = "def function():\n" + ("    x = 1\n" * 10)
            snippets.append(snippet)
        
        t0 = time.time()
        try:
            r = await cli.post(PROXY, json={"sequences": snippets},
                             headers={"X-Customer-Id": "B"}, timeout=10)
            if r.status_code == 200:
                lat = (time.time() - t0) * 1_000
                data = r.json()
                collector.add_customer_b(lat, data['proxy_latency_ms'])
                print(f"B: {num_sequences} seqs done in {lat:6.1f} ms "
                      f"(proxy said {data['proxy_latency_ms']} ms)")
            else:
                print(f"B: Error {r.status_code}: {r.text}")
        except Exception as e:
            print(f"B: Exception: {e}")
        
        # Medium frequency - approximately 1.5 requests per second
        await asyncio.sleep(0.67)

def change_strategy(strategy: str) -> bool:
    """Change proxy strategy"""
    try:
        # The endpoint expects a query parameter
        response = requests.post(f"{STRATEGY_URL}?new_strategy={strategy}", timeout=5)
        if response.status_code == 200:
            print(f"✅ Changed strategy to: {strategy}")
            return True
        else:
            print(f"❌ Failed to change strategy: {response.status_code}")
            print(f"   Response: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error changing strategy: {e}")
        return False

async def test_strategy(strategy: str, duration: float) -> LatencyCollector:
    """Test a single strategy for the given duration"""
    print(f"\n{'='*60}")
    print(f"Testing strategy: {strategy.upper()}")
    print(f"Duration: {duration} seconds")
    print('='*60)
    
    # Change strategy
    if not change_strategy(strategy):
        raise Exception(f"Failed to change to strategy: {strategy}")
    
    # Wait a moment for strategy change to take effect
    await asyncio.sleep(1)
    
    # Start data collection
    collector = LatencyCollector()
    
    async with httpx.AsyncClient(timeout=None) as cli:
        # Run both customers concurrently
        await asyncio.gather(
            customer_a(cli, collector, duration),
            customer_b(cli, collector, duration)
        )
    
    print(f"\n📊 Strategy {strategy} completed:")
    print(f"   Customer A: {len(collector.customer_a_data)} requests")
    print(f"   Customer B: {len(collector.customer_b_data)} requests")
    
    return collector

def generate_plots(results: Dict[str, LatencyCollector]):
    """Generate comparison plots for all strategies"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Set up the plot style
    plt.style.use('default')
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle('Proxy Strategy Latency Comparison', fontsize=16, fontweight='bold')
    
    # Colors for each strategy
    colors = {'sjf': '#1f77b4', 'fair': '#ff7f0e', 'fcfs': '#2ca02c'}
    
    # Plot 1: Overall latency distribution
    ax1 = axes[0, 0]
    all_latencies = {}
    for strategy, collector in results.items():
        latencies = ([d['total_latency'] for d in collector.customer_a_data] + 
                    [d['total_latency'] for d in collector.customer_b_data])
        all_latencies[strategy] = latencies
        ax1.hist(latencies, bins=30, alpha=0.7, label=strategy.upper(), 
                color=colors[strategy])
    
    ax1.set_xlabel('Total Latency (ms)')
    ax1.set_ylabel('Frequency')
    ax1.set_title('Overall Latency Distribution')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    # Plot 2: Customer A vs Customer B latency
    ax2 = axes[0, 1]
    strategies_list = list(results.keys())
    customer_a_means = []
    customer_b_means = []
    customer_a_stds = []
    customer_b_stds = []
    
    for strategy in strategies_list:
        collector = results[strategy]
        a_latencies = [d['total_latency'] for d in collector.customer_a_data]
        b_latencies = [d['total_latency'] for d in collector.customer_b_data]
        
        customer_a_means.append(np.mean(a_latencies) if a_latencies else 0)
        customer_b_means.append(np.mean(b_latencies) if b_latencies else 0)
        customer_a_stds.append(np.std(a_latencies) if a_latencies else 0)
        customer_b_stds.append(np.std(b_latencies) if b_latencies else 0)
    
    x = np.arange(len(strategies_list))
    width = 0.35
    
    ax2.bar(x - width/2, customer_a_means, width, yerr=customer_a_stds,
            label='Customer A (Short)', color='skyblue', capsize=5)
    ax2.bar(x + width/2, customer_b_means, width, yerr=customer_b_stds,
            label='Customer B (Large)', color='lightcoral', capsize=5)
    
    ax2.set_xlabel('Strategy')
    ax2.set_ylabel('Mean Latency (ms)')
    ax2.set_title('Customer Comparison by Strategy')
    ax2.set_xticks(x)
    ax2.set_xticklabels([s.upper() for s in strategies_list])
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    # Plot 3: Latency over time
    ax3 = axes[1, 0]
    for strategy, collector in results.items():
        # Customer A
        if collector.customer_a_data:
            timestamps = [d['timestamp'] for d in collector.customer_a_data]
            latencies = [d['total_latency'] for d in collector.customer_a_data]
            ax3.plot(timestamps, latencies, 'o-', label=f'{strategy.upper()} - Customer A',
                    color=colors[strategy], alpha=0.7, markersize=4)
        
        # Customer B
        if collector.customer_b_data:
            timestamps = [d['timestamp'] for d in collector.customer_b_data]
            latencies = [d['total_latency'] for d in collector.customer_b_data]
            ax3.plot(timestamps, latencies, 's-', label=f'{strategy.upper()} - Customer B',
                    color=colors[strategy], alpha=0.7, markersize=4, linestyle='--')
    
    ax3.set_xlabel('Time (seconds)')
    ax3.set_ylabel('Latency (ms)')
    ax3.set_title('Latency Over Time')
    ax3.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
    ax3.grid(True, alpha=0.3)
    
    # Plot 4: Summary statistics
    ax4 = axes[1, 1]
    stats_data = []
    labels = []
    
    for strategy in strategies_list:
        collector = results[strategy]
        all_latencies = ([d['total_latency'] for d in collector.customer_a_data] + 
                        [d['total_latency'] for d in collector.customer_b_data])
        if all_latencies:
            stats_data.append(all_latencies)
            labels.append(strategy.upper())
    
    if stats_data:
        box_plot = ax4.boxplot(stats_data, labels=labels, patch_artist=True)
        for patch, strategy in zip(box_plot['boxes'], strategies_list):
            patch.set_facecolor(colors[strategy])
            patch.set_alpha(0.7)
    
    ax4.set_xlabel('Strategy')
    ax4.set_ylabel('Latency (ms)')
    ax4.set_title('Latency Distribution (Box Plot)')
    ax4.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save the plot
    filename = f"{timestamp}_latency_comparison.png"
    filepath = os.path.join(RESULTS_DIR, filename)
    plt.savefig(filepath, dpi=300, bbox_inches='tight')
    print(f"📈 Saved plot: {filepath}")
    
    # Generate summary statistics
    summary_file = os.path.join(RESULTS_DIR, f"{timestamp}_summary.txt")
    with open(summary_file, 'w') as f:
        f.write("Proxy Strategy Latency Analysis Summary\n")
        f.write("=" * 50 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Test Duration: {TEST_DURATION} seconds per strategy\n\n")
        
        for strategy, collector in results.items():
            f.write(f"\n{strategy.upper()} Strategy:\n")
            f.write("-" * 20 + "\n")
            
            a_latencies = [d['total_latency'] for d in collector.customer_a_data]
            b_latencies = [d['total_latency'] for d in collector.customer_b_data]
            all_latencies = a_latencies + b_latencies
            
            f.write(f"Total requests: {len(all_latencies)}\n")
            f.write(f"Customer A requests: {len(a_latencies)}\n")
            f.write(f"Customer B requests: {len(b_latencies)}\n")
            
            if all_latencies:
                f.write(f"Overall mean latency: {np.mean(all_latencies):.2f} ms\n")
                f.write(f"Overall median latency: {np.median(all_latencies):.2f} ms\n")
                f.write(f"Overall std deviation: {np.std(all_latencies):.2f} ms\n")
                f.write(f"Overall min latency: {np.min(all_latencies):.2f} ms\n")
                f.write(f"Overall max latency: {np.max(all_latencies):.2f} ms\n")
            
            if a_latencies:
                f.write(f"Customer A mean: {np.mean(a_latencies):.2f} ms\n")
                f.write(f"Customer A median: {np.median(a_latencies):.2f} ms\n")
            
            if b_latencies:
                f.write(f"Customer B mean: {np.mean(b_latencies):.2f} ms\n")
                f.write(f"Customer B median: {np.median(b_latencies):.2f} ms\n")
    
    print(f"📄 Saved summary: {summary_file}")
    
    plt.show()

async def main():
    """Main analysis function"""
    print("🚀 Starting Proxy Strategy Latency Analysis")
    print(f"📊 Testing strategies: {', '.join(STRATEGIES)}")
    print(f"⏱️  Duration per strategy: {TEST_DURATION} seconds")
    
    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Test each strategy
    results = {}
    for strategy in STRATEGIES:
        try:
            results[strategy] = await test_strategy(strategy, TEST_DURATION)
        except Exception as e:
            print(f"❌ Failed to test strategy {strategy}: {e}")
            continue
    
    if not results:
        print("❌ No successful tests completed!")
        return
    
    print(f"\n🎉 All tests completed! Generating plots...")
    generate_plots(results)
    
    print(f"\n📈 Analysis complete! Check the '{RESULTS_DIR}' folder for results.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️  Analysis interrupted by user")
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        raise 