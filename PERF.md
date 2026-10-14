# ExamForge v2.0 Performance & Compute Tiers

ExamForge is optimized for lightweight execution across CPU-only developer workstations, standard servers, and GPU clusters.

---

## 1. Compute Tiers

ExamForge provides three declarative compute tiers:

| Tier | Target Machine | RAM Ceiling | OCR Workers | Table Vectorizer | Feature Caps |
|---|---|---|---|---|---|
| `lite` | Laptops, low-RAM VMs (<= 4 GB RAM) | 2.5 GB | 1 process | Simplified grid | Memory-efficient streaming |
| `standard` | Developer workstation (8–16 GB RAM) | 6.0 GB | 2 processes | Full vector lines | Full feature set (default) |
| `gpu` | High-throughput server with CUDA | 16.0 GB | 4+ processes | Full vector lines | Batched ONNX/GPU OCR |

Specify compute tier on execution:
```bash
examforge execute paper.pdf --compute lite
```

---

## 2. Low-Resource Optimization Practices

- **Streaming & Chunking**: Pages are parsed and cleaned sequentially; document snapshots are written to disk to allow Python garbage collection between stages.
- **50MP Image Bomb Protection**: `inspect_and_repair_input` checks decompression dimensions before rendering pages into memory, defending against memory exhaustion.
- **In-Memory Cache Sizing**: Figure rasterization caches and font maps maintain LRU size limits.
- **Vector-First Figure Extraction**: PyMuPDF vector drawing primitives (`get_drawings()`) are analyzed directly from PDF bytecode, avoiding expensive high-DPI full-page rasterization whenever vector paths exist.
