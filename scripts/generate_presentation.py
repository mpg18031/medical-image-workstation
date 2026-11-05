#!/usr/bin/env python3
"""
Generate an executive, publication-grade PowerPoint Case Study Presentation (.pptx and .odp).
Calibrated for Staff / Principal Systems Architect and Engineering Leadership case study rounds.
"""

import os
import subprocess
import zipfile

ODP_FILENAME = "MIVW_Systems_Architecture_Case_Study.odp"
PPTX_FILENAME = "MIVW_Systems_Architecture_Case_Study.pptx"
PDF_FILENAME = "MIVW_Systems_Architecture_Case_Study.pdf"

# 1. mimetype (must be uncompressed at offset 0)
MIMETYPE = b"application/vnd.oasis.opendocument.presentation"

# 2. META-INF/manifest.xml
MANIFEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/" manifest:version="1.2" manifest:media-type="application/vnd.oasis.opendocument.presentation"/>
  <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>
  <manifest:file-entry manifest:full-path="meta.xml" manifest:media-type="text/xml"/>
</manifest:manifest>
"""

# 3. meta.xml
META_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                      xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
                      xmlns:dc="http://purl.org/dc/elements/1.1/"
                      office:version="1.2">
  <office:meta>
    <dc:title>MIVW Systems Architecture &amp; Engineering Case Study</dc:title>
    <dc:creator>Staff / Principal Systems Architect</dc:creator>
  </office:meta>
</office:document-meta>
"""

# 4. styles.xml
STYLES_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-styles xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                        xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
                        xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
                        xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
                        xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
                        xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
                        office:version="1.2">
  <office:font-face-decls>
    <style:font-face style:name="Calibri" svg:font-family="Calibri, 'Liberation Sans', sans-serif"/>
    <style:font-face style:name="Arial" svg:font-family="Arial, 'Liberation Sans', sans-serif"/>
  </office:font-face-decls>
  <office:styles>
    <style:default-style style:family="graphic">
      <style:graphic-properties svg:stroke-color="#cbd5e1" draw:fill-color="#ffffff"/>
    </style:default-style>
  </office:styles>
  <office:automatic-styles>
    <style:page-layout style:name="pm1">
      <style:page-layout-properties fo:page-width="11.0in" fo:page-height="6.1875in"
                                    fo:margin-top="0in" fo:margin-bottom="0in"
                                    fo:margin-left="0in" fo:margin-right="0in"/>
    </style:page-layout>
  </office:automatic-styles>
  <office:master-styles>
    <style:master-page style:name="Default" style:page-layout-name="pm1"/>
  </office:master-styles>
</office:document-styles>
"""


def create_slide(title, subtitle, content_blocks, is_title_slide=False):
    """
    Generate XML for a 16:9 presentation slide.
    content_blocks is a list of tuples: (box_title, [bullets or text])
    """
    if is_title_slide:
        return f"""
      <draw:page draw:name="Slide_Title" draw:master-page-name="Default">
        <!-- Background Banner -->
        <draw:rect svg:x="0in" svg:y="0in" svg:width="11.0in" svg:height="6.1875in" draw:style-name="gr_title_bg"/>
        <!-- Title Box -->
        <draw:frame svg:x="0.8in" svg:y="1.5in" svg:width="9.4in" svg:height="3.2in">
          <draw:text-box>
            <text:p text:style-name="P_Title_Main">{title}</text:p>
            <text:p text:style-name="P_Title_Sub">{subtitle}</text:p>
            <text:p text:style-name="P_Title_Meta">Staff / Principal Systems Architecture Case Study | Real-Time GPU Computing &amp; Systems Modernization</text:p>
          </draw:text-box>
        </draw:frame>
      </draw:page>
        """

    # Standard Content Slide
    blocks_xml = ""
    num_blocks = len(content_blocks)

    if num_blocks == 1:
        # Full width block
        box_title, items = content_blocks[0]
        items_p = "".join(
            [f'<text:p text:style-name="P_Bullet">• {item}</text:p>' for item in items]
        )
        blocks_xml = f"""
        <draw:frame svg:x="0.8in" svg:y="1.4in" svg:width="9.4in" svg:height="4.2in" draw:style-name="gr_card">
          <draw:text-box>
            <text:p text:style-name="P_Card_Title">{box_title}</text:p>
            {items_p}
          </draw:text-box>
        </draw:frame>
        """
    elif num_blocks == 2:
        # 2 Column layout
        col_w = 4.5
        gap = 0.4
        for idx, (b_title, items) in enumerate(content_blocks):
            pos_x = 0.8 + idx * (col_w + gap)
            items_p = "".join(
                [f'<text:p text:style-name="P_Bullet">• {item}</text:p>' for item in items]
            )
            blocks_xml += f"""
        <draw:frame svg:x="{pos_x:.2f}in" svg:y="1.4in" svg:width="{col_w:.2f}in" svg:height="4.2in" draw:style-name="gr_card">
          <draw:text-box>
            <text:p text:style-name="P_Card_Title">{b_title}</text:p>
            {items_p}
          </draw:text-box>
        </draw:frame>
            """
    elif num_blocks == 3:
        # 3 Column layout
        col_w = 2.93
        gap = 0.3
        for idx, (b_title, items) in enumerate(content_blocks):
            pos_x = 0.8 + idx * (col_w + gap)
            items_p = "".join(
                [f'<text:p text:style-name="P_Bullet">• {item}</text:p>' for item in items]
            )
            blocks_xml += f"""
        <draw:frame svg:x="{pos_x:.2f}in" svg:y="1.4in" svg:width="{col_w:.2f}in" svg:height="4.2in" draw:style-name="gr_card">
          <draw:text-box>
            <text:p text:style-name="P_Card_Title">{b_title}</text:p>
            {items_p}
          </draw:text-box>
        </draw:frame>
            """

    return f"""
      <draw:page draw:name="Slide" draw:master-page-name="Default">
        <!-- Slide Top Header Bar -->
        <draw:rect svg:x="0in" svg:y="0in" svg:width="11.0in" svg:height="1.15in" draw:style-name="gr_header_bg"/>
        <draw:frame svg:x="0.8in" svg:y="0.18in" svg:width="9.4in" svg:height="0.85in">
          <draw:text-box>
            <text:p text:style-name="P_Slide_Title">{title}</text:p>
            <text:p text:style-name="P_Slide_Subtitle">{subtitle}</text:p>
          </draw:text-box>
        </draw:frame>
        {blocks_xml}
      </draw:page>
    """


def generate_slides():
    slides = []

    # Slide 1: Title
    slides.append(
        create_slide(
            "Real-Time Spatial Data Processing &amp; 3D Analytics Workstation (MIVW)",
            "Architecture, Performance Engineering, Systems Decoupling &amp; Business Outcomes",
            [],
            is_title_slide=True,
        )
    )

    # Slide 2: Problem Statement & Motivation
    slides.append(
        create_slide(
            "1. Problem Statement &amp; Business Motivation",
            "Overcoming legacy desktop bottlenecks under strict latency and memory constraints",
            [
                (
                    "The Legacy Monolith Problem",
                    [
                        "<text:span text:style-name='T_Bold'>High Computational Burden:</text:span> Ingesting 512³ 3D spatial volumes (256MB+ per volume) causes severe memory bloat and UI thread starvation in legacy desktop software.",
                        "<text:span text:style-name='T_Bold'>Fragile Monolithic Coupling:</text:span> Tangled numerical solvers, rendering loops, and UI controls prevent cross-platform execution and cloud deployment.",
                        "<text:span text:style-name='T_Bold'>Hardware Cost Barrier:</text:span> Requiring high-end local workstations ($10k+/seat) severely restricts deployment scale across distributed teams.",
                    ],
                ),
                (
                    "Core Engineering Objectives",
                    [
                        "<text:span text:style-name='T_Bold'>Sub-Millisecond Interactivity:</text:span> Achieve deterministic 60+ FPS volume visualization with zero UI thread contention.",
                        "<text:span text:style-name='T_Bold'>Zero-Copy Memory Interop:</text:span> Eliminate multi-hundred-megabyte IPC serialization overhead across language boundaries.",
                        "<text:span text:style-name='T_Bold'>Deployment Versatility:</text:span> Support both local GPU workstations and remote mTLS thin-client streaming from a single unified codebase.",
                        "<text:span text:style-name='T_Bold'>Production-Grade Security:</text:span> Enforce zero-leak multi-tenancy at the database layer rather than relying on application code.",
                    ],
                ),
            ],
        )
    )

    # Slide 3: 4-Tier System Architecture
    slides.append(
        create_slide(
            "2. Multi-Tier Systems Architecture",
            "End-to-end separation of presentation, coordination, native compute, and persistence",
            [
                (
                    "Presentation &amp; Client Tier",
                    [
                        "<text:span text:style-name='T_Bold'>Stack:</text:span> Electron + Vue 3 + Quasar + Pinia.",
                        "<text:span text:style-name='T_Bold'>Security Sandbox:</text:span> contextIsolation enabled, nodeIntegration disabled, preloaded IPC bridge.",
                        "<text:span text:style-name='T_Bold'>Memory Hygiene:</text:span> Client acts as a thin display tier; raw volume pixels never persist to client disk.",
                    ],
                ),
                (
                    "Gateway &amp; Compute Core",
                    [
                        "<text:span text:style-name='T_Bold'>Gateway (Python 3.12):</text:span> FastAPI AsyncIO coordination, WebSocket telemetry streaming, RFC 7807 problem details.",
                        "<text:span text:style-name='T_Bold'>Compute Core (C++20/CUDA):</text:span> High-throughput spatial processing, window-leveling kernels, central-difference gradients.",
                        "<text:span text:style-name='T_Bold'>Graphics (Vulkan 1.3):</text:span> Off-screen SPIR-V raymarching pipeline with empty-space skipping.",
                    ],
                ),
                (
                    "Data &amp; Persistence Tier",
                    [
                        "<text:span text:style-name='T_Bold'>Relational Tier:</text:span> PostgreSQL 18 with enforced Row-Level Security (FORCE RLS) and pgcrypto.",
                        "<text:span text:style-name='T_Bold'>Object Store:</text:span> Content-addressed S3/MinIO bucket (SHA-256 keys) eliminating path traversal.",
                        "<text:span text:style-name='T_Bold'>Time-Series Storage:</text:span> TimescaleDB write-behind batch logging for high-frequency metrics.",
                    ],
                ),
            ],
        )
    )

    # Slide 4: Architectural Trade-Off: In-Process pybind11 vs gRPC
    slides.append(
        create_slide(
            "3. Key Trade-Off: In-Process Interop vs. Microservices (ADR 0002)",
            "Why zero-copy in-process bindings outperformed microservice sidecars",
            [
                (
                    "Option A: gRPC Microservice Sidecar",
                    [
                        "<text:span text:style-name='T_Bold'>Theoretical Benefit:</text:span> Strong process isolation; a C++ crash cannot take down the web gateway.",
                        "<text:span text:style-name='T_Bold'>Fatal Bottleneck:</text:span> A 512³ int16 volume is 256MB. Protobuf serialization and loopback network hopping costs 200–400ms and doubles peak RAM usage.",
                        "<text:span text:style-name='T_Bold'>Cache Thrashing:</text:span> Massive memory copying severely degrades CPU L3 cache residency for concurrent requests.",
                        "<text:span text:style-name='T_Bold'>Verdict:</text:span> <text:span text:style-name='T_Reject'>REJECTED</text:span> due to unacceptable hot-path latency.",
                    ],
                ),
                (
                    "Option B: In-Process pybind11 ABI Bridge",
                    [
                        "<text:span text:style-name='T_Bold'>Zero-Copy Memory:</text:span> NumPy array views wrap native C++ volume memory buffers directly with zero copy overhead.",
                        "<text:span text:style-name='T_Bold'>GIL Discipline:</text:span> Every blocking C++ operation uses py::call_guard&lt;py::gil_scoped_release&gt; to keep AsyncIO event loops responsive.",
                        "<text:span text:style-name='T_Bold'>Failure Mitigation:</text:span> Robust C++ RAII, structured exception translation, and AddressSanitizer/UBSan validation in CI.",
                        "<text:span text:style-name='T_Bold'>Verdict:</text:span> <text:span text:style-name='T_Adopt'>ADOPTED</text:span> — cuts interop transfer time from 300ms to &lt; 0.1ms.",
                    ],
                ),
            ],
        )
    )

    # Slide 5: Vulkan 3D Raymarching & Empty-Space Skipping
    slides.append(
        create_slide(
            "4. GPU Optimization: Vulkan 1.3 Empty-Space Skipping",
            "Accelerating 3D volumetric raymarching through coarse 3D occupancy grids",
            [
                (
                    "The Volumetric Raymarching Challenge",
                    [
                        "<text:span text:style-name='T_Bold'>Brute-Force Cost:</text:span> Stepping through a 512³ volume at Nyquist sampling requires hundreds of trilinear texture samples per ray.",
                        "<text:span text:style-name='T_Bold'>Redundant Computations:</text:span> Typical spatial datasets contain 60–80% empty background (air/empty space), which wastes GPU memory bandwidth.",
                        "<text:span text:style-name='T_Bold'>Thermal &amp; Power Impact:</text:span> Continuous brute-force raymarching causes severe GPU thermal throttling on workstation hardware.",
                    ],
                ),
                (
                    "Two-Stage Acceleration Pipeline",
                    [
                        "<text:span text:style-name='T_Bold'>Pass 1 — 3D Occupancy Grid:</text:span> Compute shader evaluates volume sub-blocks, generating a compact 3D boolean occupancy texture.",
                        "<text:span text:style-name='T_Bold'>Pass 2 — Raymarching with Macro Stepping:</text:span> Fragment shader raymarcher queries the occupancy texture to skip empty macro-cells in single steps.",
                        "<text:span text:style-name='T_Bold'>Early Ray Termination:</text:span> Loop breaks instantly once accumulated opacity hits threshold (alpha &gt; 0.98).",
                        "<text:span text:style-name='T_Bold'>Outcome:</text:span> Consistent 60+ FPS interactive rendering with 3x–4x reduction in GPU texture lookups.",
                    ],
                ),
            ],
        )
    )

    # Slide 6: Lock-Free Concurrency & Memory Layout
    slides.append(
        create_slide(
            "5. Concurrency Engineering: Lock-Free SPSC Ring Buffer",
            "Eliminating CPU thread contention and false sharing on the streaming path",
            [
                (
                    "Contention &amp; False Sharing Pitfalls",
                    [
                        "<text:span text:style-name='T_Bold'>Mutex Convoying:</text:span> Traditional lock-based thread queues stall high-frequency frame producers when consumers are under load.",
                        "<text:span text:style-name='T_Bold'>False Sharing Vulnerability:</text:span> When producer and consumer atomic pointers share a single 64-byte CPU cache line, multi-core cache invalidations degrade throughput.",
                    ],
                ),
                (
                    "Lock-Free SPSC Architectural Solution",
                    [
                        "<text:span text:style-name='T_Bold'>Single-Producer Single-Consumer (SPSC):</text:span> Ring buffer design utilizing atomic load/store operations with acquire-release memory order semantics.",
                        "<text:span text:style-name='T_Bold'>Explicit Cache-Line Padding:</text:span> Applied alignas(64) to head and tail atomic pointers to guarantee physical separation across distinct CPU L1 cache lines.",
                        "<text:span text:style-name='T_Bold'>Lossy Frame Promotion:</text:span> Stale frames automatically drop under network backpressure, ensuring the client always views the latest analytical frame.",
                    ],
                ),
            ],
        )
    )

    # Slide 7: Database Multi-Tenancy & Security
    slides.append(
        create_slide(
            "6. Enterprise Security: Defense-in-Depth Multi-Tenancy",
            "Enforcing zero-leak isolation at the PostgreSQL database engine boundary",
            [
                (
                    "PostgreSQL 18 Row-Level Security (RLS)",
                    [
                        "<text:span text:style-name='T_Bold'>FORCE RLS Enforcement:</text:span> Applied ALTER TABLE ... FORCE ROW LEVEL SECURITY across all tenant tables, preventing even table owners from bypassing tenant boundaries.",
                        "<text:span text:style-name='T_Bold'>Transaction-Local Roles:</text:span> Queries execute within tenant_transaction using SET LOCAL ROLE mivw_app, automatically unwinding state at COMMIT/ROLLBACK to prevent pooled connection state leakage.",
                        "<text:span text:style-name='T_Bold'>Stale Plan Mitigation:</text:span> Configured statement_cache_size = 0 in asyncpg to eliminate risks of cached execution plans carrying cross-tenant contexts.",
                    ],
                ),
                (
                    "Storage &amp; Transport Cryptography",
                    [
                        "<text:span text:style-name='T_Bold'>Content-Addressed Storage:</text:span> Object store keys derived strictly from payload SHA-256 hashes, completely eliminating path traversal vulnerabilities.",
                        "<text:span text:style-name='T_Bold'>Column-Level Encryption:</text:span> Direct patient identifiers encrypted at rest using pgcrypto with keys stored outside database records.",
                        "<text:span text:style-name='T_Bold'>Presigned URL Security:</text:span> Client uploads and downloads bypass API servers via short-lived (15-minute) presigned S3 URLs, isolating the gateway from large binary payloads.",
                    ],
                ),
            ],
        )
    )

    # Slide 8: Domain Integrity & Healthcare Compliance
    slides.append(
        create_slide(
            "7. Healthcare Domain Engineering &amp; Regulatory Boundaries",
            "Addressing real-world compliance hazards: DICOM PS3.15 and burned-in annotations",
            [
                (
                    "Automated PS3.15 De-Identification",
                    [
                        "<text:span text:style-name='T_Bold'>DICOM PS3.15 Annex E Basic Profile:</text:span> C++ ingest engine strips direct patient identifiers, cleans private tags, and normalizes acquisition metadata.",
                        "<text:span text:style-name='T_Bold'>Cryptographic Pseudonymization:</text:span> Study/Series UIDs and Patient IDs are replaced with deterministic 2.25.&lt;hash&gt; representations, preserving relational hierarchy while ensuring irreversibility.",
                    ],
                ),
                (
                    "The Burned-In Pixel Hazard &amp; RUO",
                    [
                        "<text:span text:style-name='T_Bold'>The Hidden PHI Hazard:</text:span> Header scrubbing alone fails when patient text is rendered directly into image pixels (common in ultrasound and fluoroscopy).",
                        "<text:span text:style-name='T_Bold'>Automated Quarantine Pipeline:</text:span> Ingest inspects BurnedInAnnotation tags and modality risk profiles, automatically routing at-risk series to quarantine.",
                        "<text:span text:style-name='T_Bold'>Regulatory Boundaries:</text:span> Explicit Research Use Only (RUO) classification with non-dismissible UI disclaimers to prevent unauthorized clinical use.",
                    ],
                ),
            ],
        )
    )

    # Slide 9: Testing Strategy & Verification
    slides.append(
        create_slide(
            "8. Quality Assurance &amp; Verification Strategy",
            "A multi-tiered test pyramid spanning unit, perceptual, contract, and E2E verification",
            [
                (
                    "Native C++ &amp; GPU Verification",
                    [
                        "<text:span text:style-name='T_Bold'>CTest / GoogleTest (52/52 Passing):</text:span> Validates spatial resampling, orientation math, and CUDA gradient/windowing kernels.",
                        "<text:span text:style-name='T_Bold'>Perceptual Golden-Image Testing:</text:span> Compares Vulkan rendered frames against golden reference images using SSIM and PSNR thresholds.",
                        "<text:span text:style-name='T_Bold'>Hardware Fault Recovery:</text:span> Explicit test suites simulate and verify recovery from GPU device loss (VK_ERROR_DEVICE_LOST).",
                    ],
                ),
                (
                    "Contract, Property &amp; E2E Testing",
                    [
                        "<text:span text:style-name='T_Bold'>Contract Fuzzing:</text:span> Schemathesis generates property-based HTTP/WebSocket requests against OpenAPI specs to find edge-case crashes.",
                        "<text:span text:style-name='T_Bold'>Frontend Unit Testing:</text:span> 92 passing Vitest unit tests verifying Pinia reactive stores and geometry coordinate math.",
                        "<text:span text:style-name='T_Bold'>Full E2E Automation:</text:span> Playwright test suites drive the packaged Electron binary across ingest, viewer, and inference workflows.",
                    ],
                ),
            ],
        )
    )

    # Slide 10: Business Outcomes & Blueprint Value
    slides.append(
        create_slide(
            "9. Business Impact &amp; Engineering Outcomes",
            "Delivering business-oriented outcomes without marketing fluff",
            [
                (
                    "Operational &amp; Cost Efficiency",
                    [
                        "<text:span text:style-name='T_Bold'>Workstation Cost Reduction:</text:span> Thin-client remote streaming decouples visualization from client hardware, allowing shared GPU nodes to replace $10k+ local engineering PCs.",
                        "<text:span text:style-name='T_Bold'>Zero Deployment Footprint:</text:span> Browser/Electron thin-client eliminates client-side driver compatibility issues and complex local software installations.",
                        "<text:span text:style-name='T_Bold'>Bandwidth Optimization:</text:span> Offloading rendering to remote GPUs streams only compressed video frames, eliminating gigabyte-scale raw dataset downloads over customer networks.",
                    ],
                ),
                (
                    "Architectural Blueprint for Modernization",
                    [
                        "<text:span text:style-name='T_Bold'>Monolith Extraction Blueprint:</text:span> Demonstrates a repeatable playbook for extracting high-performance computational engines from legacy desktop CAD/CAE monoliths.",
                        "<text:span text:style-name='T_Bold'>Unified Codebase:</text:span> A single architecture supports both standalone offline workstations and multi-tenant cloud deployments via runtime configuration (MIVW_MODE).",
                        "<text:span text:style-name='T_Bold'>Rapid Feature Iteration:</text:span> Decoupling compute from UI enables independent release cadences across backend solver teams and frontend UI teams.",
                    ],
                ),
            ],
        )
    )

    # Slide 11: Retrospective & Future Roadmap
    slides.append(
        create_slide(
            "10. Architectural Retrospective &amp; Next Horizons",
            "Honest technical lessons learned and forward-looking roadmap",
            [
                (
                    "Lessons Learned &amp; Trade-Off Reflections",
                    [
                        "<text:span text:style-name='T_Bold'>C++ / Python ABI Coupling:</text:span> In-process bindings require exact synchronization between Python runtime ABIs and C++ compilers. Containerized hermetic wheel builds are essential.",
                        "<text:span text:style-name='T_Bold'>Dynamic Dimension Handling:</text:span> Fixed-dimension ONNX models cause production runtime mismatches; dynamic spatial dimensioning with tensor validation must be enforced at ingest.",
                        "<text:span text:style-name='T_Bold'>Frontend Coverage Targets:</text:span> Viewport reactive stores require expanded state-machine testing to meet rigorous 80%+ coverage bars.",
                    ],
                ),
                (
                    "Future Technical Horizons",
                    [
                        "<text:span text:style-name='T_Bold'>Multi-GPU Spatial Slicing:</text:span> Distribute massive 1024³+ spatial volumes across NVLink-connected GPUs for sub-millisecond multi-planar reformatting.",
                        "<text:span text:style-name='T_Bold'>WebGPU Client Fallback:</text:span> Implement WebGPU in-browser compute shaders as a fallback execution mode when remote GPU nodes are unavailable.",
                        "<text:span text:style-name='T_Bold'>Automated Model Quantization:</text:span> Integrate TensorRT FP16/INT8 dynamic post-training quantization to reduce inference VRAM footprint by 50%.",
                    ],
                ),
            ],
        )
    )

    # Slide 12: Summary & Q&A
    slides.append(
        create_slide(
            "11. Summary &amp; Technical Discussion",
            "Core takeaways: Performance, modularity, security, and discipline",
            [
                (
                    "Key Takeaways",
                    [
                        "<text:span text:style-name='T_Bold'>High-Performance Core:</text:span> Vulkan empty-space skipping, lock-free SPSC concurrency, and pybind11 zero-copy interop solve the 3D data latency bottleneck.",
                        "<text:span text:style-name='T_Bold'>Enterprise Security:</text:span> PostgreSQL 18 Row-Level Security, pgcrypto, and DICOM PS3.15 de-identification enforce compliance at the persistence tier.",
                        "<text:span text:style-name='T_Bold'>Engineering Discipline:</text:span> 52/52 passing CTest suite with perceptual image testing, contract fuzzing, and complete ADR documentation.",
                    ],
                ),
                (
                    "Open for Deep-Dive Q&amp;A",
                    [
                        "• Deep-dive into CUDA/Vulkan compute shaders and raymarching memory layout.",
                        "• Architectural exploration of pybind11 vs. shared-memory IPC trade-offs.",
                        "• Database multi-tenancy, connection pooling, and RLS enforcement mechanics.",
                        "• Scaling strategies for multi-GPU spatial computing and cloud rendering.",
                    ],
                ),
            ],
        )
    )

    return "\n".join(slides)


CONTENT_XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                         xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
                         xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
                         xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
                         xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
                         xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
                         xmlns:xlink="http://www.w3.org/1999/xlink"
                         office:version="1.2">
  <office:font-face-decls>
    <style:font-face style:name="Calibri" svg:font-family="Calibri, 'Liberation Sans', sans-serif"/>
  </office:font-face-decls>

  <office:automatic-styles>
    <!-- Text Styles -->
    <style:style style:name="T_Bold" style:family="text">
      <style:text-properties fo:font-weight="bold" fo:color="#0f172a"/>
    </style:style>
    <style:style style:name="T_Adopt" style:family="text">
      <style:text-properties fo:font-weight="bold" fo:color="#0f766e"/>
    </style:style>
    <style:style style:name="T_Reject" style:family="text">
      <style:text-properties fo:font-weight="bold" fo:color="#b91c1c"/>
    </style:style>

    <!-- Graphic Styles for Boxes -->
    <style:style style:name="gr_title_bg" style:family="graphic">
      <style:graphic-properties draw:fill="solid" draw:fill-color="#0f172a" svg:stroke-color="none"/>
    </style:style>
    <style:style style:name="gr_header_bg" style:family="graphic">
      <style:graphic-properties draw:fill="solid" draw:fill-color="#0f172a" svg:stroke-color="none"/>
    </style:style>
    <style:style style:name="gr_card" style:family="graphic">
      <style:graphic-properties draw:fill="solid" draw:fill-color="#f8fafc"
                                svg:stroke-color="#cbd5e1" svg:stroke-width="1.2pt"
                                fo:padding="12pt"/>
    </style:style>

    <!-- Paragraph Styles -->
    <style:style style:name="P_Title_Main" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="0pt" fo:margin-bottom="8pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="24pt" fo:font-weight="bold" fo:color="#f8fafc"/>
    </style:style>
    <style:style style:name="P_Title_Sub" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="0pt" fo:margin-bottom="16pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="13pt" fo:color="#38bdf8"/>
    </style:style>
    <style:style style:name="P_Title_Meta" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="0pt" fo:margin-bottom="0pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="10.5pt" fo:font-style="italic" fo:color="#94a3b8"/>
    </style:style>

    <style:style style:name="P_Slide_Title" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="0pt" fo:margin-bottom="2pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="17pt" fo:font-weight="bold" fo:color="#ffffff"/>
    </style:style>
    <style:style style:name="P_Slide_Subtitle" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="0pt" fo:margin-bottom="0pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="10pt" fo:color="#38bdf8"/>
    </style:style>

    <style:style style:name="P_Card_Title" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="0pt" fo:margin-bottom="8pt"
                                  fo:border-bottom="1.5pt solid #0f766e" fo:padding-bottom="3pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="12pt" fo:font-weight="bold" fo:color="#0f766e"/>
    </style:style>
    <style:style style:name="P_Bullet" style:family="paragraph">
      <style:paragraph-properties fo:margin-left="0.2in" fo:text-indent="-0.2in"
                                  fo:margin-top="3pt" fo:margin-bottom="5pt" fo:line-height="125%"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9.8pt" fo:color="#334155"/>
    </style:style>
  </office:automatic-styles>

  <office:body>
    <office:presentation>
      {generate_slides()}
    </office:presentation>
  </office:body>
</office:document-content>
"""


def generate_presentation():
    print(f"Creating {ODP_FILENAME}...")
    with zipfile.ZipFile(ODP_FILENAME, "w") as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/manifest.xml",
            MANIFEST_XML.strip(),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        zf.writestr("meta.xml", META_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("styles.xml", STYLES_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("content.xml", CONTENT_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)

    print(f"Successfully generated {ODP_FILENAME} ({os.path.getsize(ODP_FILENAME)} bytes).")

    # Convert to PPTX
    print("Converting to PowerPoint (.pptx)...")
    res_pptx = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pptx", ODP_FILENAME],
        check=False,
        capture_output=True,
        text=True,
    )
    if res_pptx.returncode == 0:
        print(f"Successfully generated {PPTX_FILENAME} ({os.path.getsize(PPTX_FILENAME)} bytes).")
    else:
        print("PPTX conversion failed:", res_pptx.stderr)

    # Convert to PDF for quick previewing
    print("Converting to PDF (.pdf)...")
    res_pdf = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", ODP_FILENAME],
        check=False,
        capture_output=True,
        text=True,
    )
    if res_pdf.returncode == 0:
        print(f"Successfully generated {PDF_FILENAME} ({os.path.getsize(PDF_FILENAME)} bytes).")
    else:
        print("PDF conversion failed:", res_pdf.stderr)


if __name__ == "__main__":
    generate_presentation()
