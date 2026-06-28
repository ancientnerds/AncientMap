# Local vs Cloud LLM Inference: Hardware Comparison (March 2026)

Research compiled March 19, 2026. All numbers sourced from real-world benchmarks, not theoretical peaks.

---

## 1. NVIDIA RTX 5090

### Specifications
| Spec | Value |
|------|-------|
| VRAM | 32 GB GDDR7 |
| Memory Bandwidth | 1,792 GB/s |
| CUDA Cores | 21,760 |
| TDP | 575W |
| PSU Requirement | 1,000W+ |
| MSRP | $1,999 |
| Street Price (Mar 2026) | $3,500-$4,200 (scalped; MSRP stock unavailable) |

### Token Generation Speed (single GPU, Q4_K_M quantization, Ollama/llama.cpp)

| Model Size | Model Example | tok/s (generation) | Notes |
|------------|---------------|-------------------|-------|
| 7-8B | Llama 3.1 8B | ~150-160 tok/s | Fits entirely in VRAM, very fast |
| 12B | Gemma 3 12B | ~70 tok/s | Comfortable fit |
| 14B | Qwen 2.5 14B / DeepSeek-R1 14B | ~85-90 tok/s | Comfortable fit |
| 27-32B | Qwen 2.5 32B / Gemma 3 27B | ~45-57 tok/s | Fits in VRAM at Q4 |
| 70B | Llama 3.3 70B (Q3/Q4) | ~20-22 tok/s* | *Extremely tight at Q4 (~43GB needed); requires aggressive quant (Q3_K_M ~30GB) or partial CPU offload. Context limited to <2K tokens. Quality noticeably degraded vs Q4_K_M. |
| 70B (2x GPU) | Llama 3.3 70B Q4 | ~27 tok/s | Dual RTX 5090 (64GB total). Beats H100 (24.3 tok/s). |

### Prompt Processing Speed (prefill, single GPU)
| Model | 4K context | 8K context | 32K context |
|-------|-----------|-----------|-------------|
| Qwen3 8B | 10,406 tok/s | 8,745 tok/s | 3,688 tok/s |
| Qwen3 14B | 6,498 tok/s | 5,594 tok/s | 2,908 tok/s |
| Qwen3 32B | 2,931 tok/s | 2,530 tok/s | 1,451 tok/s |

### Largest Model That Fits in 32GB VRAM
- **Sweet spot**: Up to ~55B parameters at Q4_K_M quantization
- **Maximum practical**: 70B at Q3_K_M (~30GB) but with severely limited context window and degraded quality
- **32B models**: Comfortable fit with room for KV cache at longer contexts
- **Cannot run**: 70B at Q4_K_M (needs ~43GB), 110B+, 405B (single GPU)

### Power & Electricity (24/7 operation)
| Metric | Value |
|--------|-------|
| Typical inference draw | 350-450W (not full 575W TDP during inference) |
| System total (GPU + CPU + etc.) | ~500-600W |
| Annual electricity (24/7, $0.18/kWh US avg) | **$788-$946/year** |
| Annual electricity (8 hrs/day, $0.18/kWh) | **$263-$315/year** |

---

## 2. Apple Mac Studio M3 Ultra (512GB Unified Memory)

### Specifications
| Spec | Value |
|------|-------|
| Chip | Apple M3 Ultra (32-core CPU, 80-core GPU) |
| Unified Memory | 512 GB LPDDR5x |
| Memory Bandwidth | 819 GB/s |
| Neural Engine | 32-core |
| Max Storage | 16 TB SSD |
| Price (512GB RAM, 80-core GPU, 1TB SSD) | $9,499 |
| Price (maxed out: 512GB RAM, 16TB SSD) | $14,099 |

**Note**: As of March 2026, there is no M4 Ultra. The current Mac Studio ships with either M4 Max (up to 128GB) or M3 Ultra (up to 512GB). The M3 Ultra is the only Apple chip that reaches 512GB.

### Token Generation Speed (MLX preferred; llama.cpp also tested)

| Model Size | Model Example | tok/s (generation) | Framework | Notes |
|------------|---------------|-------------------|-----------|-------|
| 7-8B | Llama 3.1 8B Q4 | ~92-110 tok/s | MLX | M4 Max slightly faster per-core |
| 14B | Various 14B | ~50-65 tok/s | MLX (est.) | Scales linearly with bandwidth |
| 32B | Qwen 2.5 32B Q4 | ~25-35 tok/s | MLX (est.) | Comfortable fit in memory |
| 70B | DeepSeek R1 70B Q4 | ~13.7 tok/s | llama.cpp | Fits entirely in unified memory -- no offloading needed |
| 70B | DeepSeek R1 70B Q4 | ~16-18 tok/s | MLX | MLX 20-30% faster than llama.cpp |
| 405B | Llama 405B Q4 | ~6-8 tok/s | MLX (est.) | Fits in 512GB. Slow but functional. |
| 671B (MoE) | DeepSeek R1 671B Q4 | ~16.1 tok/s | llama.cpp | MoE architecture helps; only active experts loaded |
| 671B (MoE) | DeepSeek R1 671B Q4 | ~18.1 tok/s | MLX | Best framework for Apple Silicon |
| 671B (dense equiv.) | DeepSeek V3 671B Q4 | ~6.2 tok/s | llama.cpp | Dense model, much slower |

### Largest Model That Fits in 512GB
- **70B unquantized (FP16)**: Yes, fits (~140GB)
- **405B at Q4**: Yes, fits (~210GB) with room for KV cache
- **671B MoE at Q4**: Yes, fits (~404GB). Barely.
- **Theoretical max**: ~600B+ parameters at Q4 quantization

### Power & Electricity (24/7 operation)
| Metric | Value |
|--------|-------|
| Idle power | ~8W |
| LLM inference load | ~150-200W |
| Peak (stress test) | ~270W |
| Annual electricity (24/7 inference, $0.18/kWh) | **$236-$315/year** |
| Annual electricity (8 hrs/day, $0.18/kWh) | **$79-$105/year** |

The Mac Studio is dramatically more power-efficient than the RTX 5090 system.

---

## 3. Cloud: Anthropic Claude API (March 2026)

### Pricing (per million tokens)

| Model | Input | Output | Batch Input | Batch Output |
|-------|-------|--------|-------------|--------------|
| **Claude Sonnet 4.6** | $3.00 | $15.00 | $1.50 | $7.50 |
| Claude Sonnet 4.5 | $3.00 | $15.00 | $1.50 | $7.50 |
| Claude Sonnet 4 | $3.00 | $15.00 | $1.50 | $7.50 |
| **Claude Haiku 4.5** | $1.00 | $5.00 | $0.50 | $2.50 |
| Claude Opus 4.6 | $5.00 | $25.00 | $2.50 | $12.50 |

### Performance

| Metric | Sonnet 4.6 | Haiku 4.5 |
|--------|-----------|-----------|
| Output speed (Anthropic API) | ~50 tok/s | ~89-106 tok/s |
| Output speed (best provider) | ~53 tok/s (Amazon) | ~99 tok/s (Amazon) |
| Time to First Token (TTFT) | 1.0-1.6s | 0.6-0.7s |
| Context window | 1M tokens | 200K tokens |
| Max output | 64K tokens | 64K tokens |

### Cost Characteristics
- Zero hardware cost
- Zero electricity cost
- Zero maintenance cost
- Pay only for what you use
- Scales to zero when idle
- Scales to thousands of concurrent requests instantly

---

## 4. Head-to-Head Comparison

### Speed: Token Generation (output tok/s)

| Model Size | RTX 5090 (1x) | Mac Studio M3 Ultra | Claude Sonnet 4.6 | Claude Haiku 4.5 |
|------------|---------------|---------------------|-------------------|-----------------|
| 8B local / Cloud equiv. | 150-160 | 92-110 | -- | -- |
| 14B | 85-90 | 50-65 | -- | -- |
| 32B | 45-57 | 25-35 | -- | -- |
| 70B | 20-22* | 14-18 | -- | -- |
| 405B | Cannot run | 6-8 | -- | -- |
| Cloud (frontier) | -- | -- | ~50 | ~90-100 |

*RTX 5090 70B requires aggressive quantization and limited context.

### Quality: Local 70B vs Cloud Frontier

| Benchmark | Llama 3.3 70B (Q4) | Qwen3 72B | Claude Sonnet 4.6 |
|-----------|--------------------|-----------|--------------------|
| MMLU | ~86% | ~88% | ~90%+ |
| HumanEval (coding) | ~80% | ~84% | ~90%+ |
| SWE-bench Verified | ~35% | ~40% | ~70%+ |
| Complex reasoning | Good | Good | Excellent |
| Instruction following | Good | Good | Excellent |

**Key quality insight**: Local 70B models are competitive on standard benchmarks (MMLU, HumanEval) but fall significantly behind frontier cloud models on complex real-world tasks (SWE-bench, multi-step reasoning, agentic workflows). The gap is most visible on novel problems, not pattern-matched ones.

### Largest Runnable Model

| Hardware | Largest Model | Speed | Usable? |
|----------|--------------|-------|---------|
| RTX 5090 (1x, 32GB) | 70B at Q3_K_M | ~20 tok/s | Barely (limited context, quality loss) |
| RTX 5090 (2x, 64GB) | 70B at Q4_K_M | ~27 tok/s | Yes, good quality |
| Mac Studio 512GB | 671B MoE (DeepSeek R1) | ~18 tok/s | Yes, impressively usable |
| Mac Studio 512GB | 405B dense (Q4) | ~6-8 tok/s | Functional but slow |
| Cloud (Claude) | Frontier models (trillions of params) | 50-100 tok/s | Best quality, always fast |

---

## 5. Total Cost of Ownership: 1-Year Analysis

### Assumptions
- US average electricity: $0.18/kWh (March 2026 national average)
- Usage pattern: 8 hours/day active inference, idle remainder
- Cloud usage: 50M output tokens/month (moderate professional use)

### RTX 5090 System Build
| Component | Cost |
|-----------|------|
| RTX 5090 GPU (street price) | $3,800 |
| CPU (Ryzen 9 / i9) | $450 |
| Motherboard | $300 |
| 64GB DDR5 RAM | $200 |
| 1000W+ PSU | $200 |
| Case + cooling | $200 |
| NVMe SSD 2TB | $150 |
| **Total hardware** | **~$5,300** |
| Electricity (1 year, 8h/day) | ~$290 |
| **Year 1 total** | **~$5,590** |

### Mac Studio M3 Ultra (512GB)
| Component | Cost |
|-----------|------|
| Mac Studio (512GB, 80-core GPU, 1TB) | $9,499 |
| **Total hardware** | **$9,499** |
| Electricity (1 year, 8h/day) | ~$92 |
| **Year 1 total** | **~$9,591** |

### Cloud: Claude Sonnet 4.6
| Component | Cost |
|-----------|------|
| Hardware | $0 |
| Electricity | $0 |
| API cost: 50M output tokens/month x $15/MTok | $750/month |
| API cost: 25M input tokens/month x $3/MTok | $75/month |
| **Year 1 total** | **~$9,900** |

### Cloud: Claude Haiku 4.5
| Component | Cost |
|-----------|------|
| Hardware | $0 |
| Electricity | $0 |
| API cost: 50M output tokens/month x $5/MTok | $250/month |
| API cost: 25M input tokens/month x $1/MTok | $25/month |
| **Year 1 total** | **~$3,300** |

### Cloud: Claude Sonnet 4.6 (Batch API, 50% off)
| Component | Cost |
|-----------|------|
| API cost: 50M output tokens/month x $7.50/MTok | $375/month |
| API cost: 25M input tokens/month x $1.50/MTok | $37.50/month |
| **Year 1 total** | **~$4,950** |

---

## 6. Decision Matrix

| Factor | RTX 5090 | Mac Studio M3 Ultra | Cloud (Sonnet 4.6) |
|--------|----------|---------------------|---------------------|
| **Best model quality** | 32B class (excellent at Q4) | 70B+ (unquantized possible) | Frontier (best available) |
| **Speed at 32B** | FASTEST (45-57 tok/s) | Moderate (25-35 tok/s) | N/A (no 32B equivalent) |
| **Speed at 70B** | Tight/marginal | Good (14-18 tok/s) | ~50 tok/s (frontier quality) |
| **Can run 405B?** | No | Yes (~6-8 tok/s) | N/A (frontier > 405B) |
| **Privacy** | Full (air-gapped possible) | Full (air-gapped possible) | Data sent to Anthropic |
| **Upfront cost** | ~$5,300 (system) | ~$9,500 | $0 |
| **Monthly operating cost** | ~$24 electricity | ~$8 electricity | $825 (Sonnet) / $275 (Haiku) |
| **Power efficiency** | Poor (350-450W inference) | Excellent (150-200W inference) | N/A |
| **Noise/heat** | Significant | Silent/minimal | N/A |
| **Availability** | Scarce, scalped | Available from Apple | Always available |
| **Scales to zero cost when idle** | No | No | Yes |
| **Year 1 TCO** | ~$5,590 | ~$9,591 | $3,300-$9,900 |

---

## 7. Key Takeaways for Presentation

1. **RTX 5090 is the speed king for models up to 32B** -- nothing beats 57 tok/s on a 32B model for ~$5K total. But its 32GB VRAM ceiling makes 70B models a painful squeeze.

2. **Mac Studio M3 Ultra is the memory king** -- 512GB unified memory means you can run models that no consumer GPU can touch (405B, 671B). The tradeoff is slower tok/s due to lower memory bandwidth (819 vs 1,792 GB/s) and a $9,500 price tag.

3. **Cloud wins on quality ceiling** -- Claude Sonnet 4.6 outperforms any local model on complex reasoning, coding, and agentic tasks. No local 70B model comes close on SWE-bench or multi-step planning.

4. **Cloud wins on flexibility** -- zero upfront cost, instant scaling, zero maintenance. But at heavy usage (50M output tokens/month), Sonnet 4.6 costs $9,900/year -- comparable to a Mac Studio.

5. **Cloud Haiku 4.5 is the value play** -- at $3,300/year for 50M tokens/month with near-Sonnet quality, it undercuts even the RTX 5090 system build on year-1 cost.

6. **Electricity matters more than you think** -- US average is now $0.18/kWh. An RTX 5090 running 24/7 costs $789-946/year in power alone. The Mac Studio costs $236-315/year for the same uptime.

7. **The real question is not speed, it's what fits** -- If your use case needs 70B+ models with full context windows, the Mac Studio is the only consumer option. If you need frontier quality, cloud is the only option. If you need fast inference on 8B-32B models, the RTX 5090 is unbeatable.

---

## Sources

All data gathered March 19, 2026 from the following sources:

### RTX 5090
- NVIDIA official specs: https://www.nvidia.com/en-us/geforce/graphics-cards/50-series/rtx-5090/
- Ollama single-GPU benchmarks: https://www.databasemart.com/blog/ollama-gpu-benchmark-rtx5090
- Ollama dual-GPU benchmarks: https://www.databasemart.com/blog/ollama-gpu-benchmark-rtx5090-2
- Hardware Corner prompt processing benchmarks: https://www.hardware-corner.net/rtx-5090-llm-benchmarks/
- Awesome Agents RTX 5090 analysis: https://awesomeagents.ai/hardware/nvidia-rtx-5090/
- RunPod RTX 5090 review: https://www.runpod.io/articles/guides/nvidia-rtx-5090
- RTX 5090 price tracker: https://bestvaluegpu.com/history/new-and-used-rtx-5090-price-history-and-specs/

### Mac Studio M3 Ultra
- Apple Mac Studio specs: https://www.apple.com/mac-studio/specs/
- Apple Mac Studio tech specs (support): https://support.apple.com/en-us/122211
- Apple newsroom announcement: https://www.apple.com/newsroom/2025/03/apple-unveils-new-mac-studio-the-most-powerful-mac-ever/
- MacRumors maxed-out pricing: https://www.macrumors.com/2025/03/05/maxed-out-m3-ultra-mac-studio-14099/
- Hostbor M3 Ultra LLM benchmarks: https://hostbor.com/mac-studio-m3-ultra-tested/
- Hardware Corner DeepSeek on M3 Ultra: https://www.hardware-corner.net/mac-studio-m3-ultra-deepseek-llamacpp/
- InsiderLLM Mac LLM guide: https://insiderllm.com/guides/best-local-llms-mac-2026/
- Apple power consumption: https://support.apple.com/en-us/102027
- llama.cpp Apple Silicon discussion: https://github.com/ggml-org/llama.cpp/discussions/4167

### Claude API
- Anthropic official pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Artificial Analysis Sonnet 4.6 benchmarks: https://artificialanalysis.ai/models/claude-sonnet-4-6/providers
- Artificial Analysis Haiku 4.5 benchmarks: https://artificialanalysis.ai/models/claude-4-5-haiku/providers
- PricePerToken Sonnet 4.6: https://pricepertoken.com/pricing-page/model/anthropic-claude-sonnet-4.6

### Electricity
- US average electricity rates March 2026: https://www.electricchoice.com/electricity-prices-by-state/

### Quality Comparisons
- Vellum LLM Leaderboard: https://www.vellum.ai/llm-leaderboard
- SitePoint best local LLMs 2026: https://www.sitepoint.com/best-local-llm-models-2026/
