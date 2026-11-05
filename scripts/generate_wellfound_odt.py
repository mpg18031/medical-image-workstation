#!/usr/bin/env python3
"""
Generate a professional, copy-paste-ready OpenDocument Text (.odt) for Wellfound (AngelList Talent).
Calibrated for Startup Founders, CTOs, and VPs of Engineering seeking Staff/Principal Systems Architects
or Founding Systems Engineers in AI Infrastructure, Spatial Computing, and High-Performance Systems.
"""

import zipfile
import os
import subprocess

ODT_FILENAME = "Wellfound_Profile_Staff_Principal_Systems_Architect.odt"
PDF_FILENAME = "Wellfound_Profile_Staff_Principal_Systems_Architect.pdf"

# 1. mimetype (must be uncompressed at offset 0)
MIMETYPE = b"application/vnd.oasis.opendocument.text"

# 2. META-INF/manifest.xml
MANIFEST_XML = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">
  <manifest:file-entry manifest:full-path="/" manifest:version="1.2" manifest:media-type="application/vnd.oasis.opendocument.text"/>
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
    <dc:title>Wellfound Profile - Staff / Principal Systems Architect</dc:title>
    <dc:creator>Staff Systems Architect</dc:creator>
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
                        office:version="1.2">
  <office:font-face-decls>
    <style:font-face style:name="Calibri" svg:font-family="Calibri, 'Liberation Sans', sans-serif"/>
  </office:font-face-decls>
  <office:styles>
    <style:default-style style:family="paragraph">
      <style:paragraph-properties fo:hyphenation-ladder-count="no-limit" fo:hyphenation-keep="auto"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="10pt" fo:color="#1e293b"/>
    </style:default-style>
  </office:styles>
  <office:automatic-styles>
    <style:page-layout style:name="pm1">
      <style:page-layout-properties fo:page-width="8.5in" fo:page-height="11in"
                                    fo:margin-top="0.6in" fo:margin-bottom="0.6in"
                                    fo:margin-left="0.65in" fo:margin-right="0.65in"/>
    </style:page-layout>
  </office:automatic-styles>
  <office:master-styles>
    <style:master-page style:name="Standard" style:page-layout-name="pm1"/>
  </office:master-styles>
</office:document-styles>
"""

# 5. content.xml
CONTENT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
                         xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0"
                         xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
                         xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
                         xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
                         xmlns:xlink="http://www.w3.org/1999/xlink"
                         office:version="1.2">
  <office:font-face-decls>
    <style:font-face style:name="Calibri" svg:font-family="Calibri, 'Liberation Sans', sans-serif"/>
  </office:font-face-decls>

  <office:automatic-styles>
    <style:style style:name="T_Bold" style:family="text">
      <style:text-properties fo:font-weight="bold"/>
    </style:style>
    <style:style style:name="T_Tag" style:family="text">
      <style:text-properties fo:font-weight="bold" fo:color="#ea580c"/>
    </style:style>
    <style:style style:name="T_Link" style:family="text">
      <style:text-properties fo:color="#0284c7" fo:text-decoration="underline"/>
    </style:style>

    <style:style style:name="P_Doc_Title" style:family="paragraph">
      <style:paragraph-properties fo:text-align="left" fo:margin-top="0pt" fo:margin-bottom="2pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="18pt" fo:font-weight="bold" fo:color="#0f172a"/>
    </style:style>

    <style:style style:name="P_Doc_Subtitle" style:family="paragraph">
      <style:paragraph-properties fo:text-align="left" fo:margin-top="0pt" fo:margin-bottom="12pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="10pt" fo:color="#64748b"/>
    </style:style>

    <style:style style:name="P_Section_Header" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="14pt" fo:margin-bottom="4pt" fo:keep-with-next="always"
                                  fo:border-bottom="1.5pt solid #ea580c" fo:padding-bottom="2pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="12pt" fo:font-weight="bold" fo:color="#ea580c" fo:letter-spacing="0.5pt"/>
    </style:style>

    <style:style style:name="P_Subsection" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="8pt" fo:margin-bottom="2pt" fo:keep-with-next="always"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="10.5pt" fo:font-weight="bold" fo:color="#1e293b"/>
    </style:style>

    <style:style style:name="P_Body" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="2pt" fo:margin-bottom="5pt" fo:line-height="125%"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9.5pt" fo:color="#334155"/>
    </style:style>

    <style:style style:name="P_Callout" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="4pt" fo:margin-bottom="6pt" fo:line-height="120%"
                                  fo:background-color="#fff7ed" fo:padding="6pt"
                                  fo:border-left="3pt solid #ea580c"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9.5pt" fo:color="#0f172a"/>
    </style:style>

    <style:style style:name="P_Bullet" style:family="paragraph">
      <style:paragraph-properties fo:margin-left="0.25in" fo:text-indent="-0.25in"
                                  fo:margin-top="2pt" fo:margin-bottom="3pt" fo:line-height="120%"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9.5pt" fo:color="#334155"/>
    </style:style>

    <style:style style:name="P_TechTags" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="2pt" fo:margin-bottom="8pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9pt" fo:font-weight="bold" fo:color="#475569"/>
    </style:style>
  </office:automatic-styles>

  <office:body>
    <office:text>
      <text:p text:style-name="P_Doc_Title">WELLFOUND (ANGELLIST) PROFILE OPTIMIZATION GUIDE</text:p>
      <text:p text:style-name="P_Doc_Subtitle">Copy-paste ready profile content calibrated for startup founders, CTOs, and VPs of Engineering at Series A–D and growth-stage companies.</text:p>

      <!-- SECTION 1: ONE-LINE PITCH -->
      <text:p text:style-name="P_Section_Header">1. ONE-LINE PITCH / TAGLINE (MAX 100 CHARACTERS)</text:p>
      <text:p text:style-name="P_Body">Wellfound prominently displays this under your name in search results and founder review queues:</text:p>

      <text:p text:style-name="P_Subsection">Option A (Recommended — High-Throughput &amp; GPU Focus):</text:p>
      <text:p text:style-name="P_Callout"><text:span text:style-name="T_Bold">Staff / Principal Systems Architect | High-Throughput C++20, CUDA &amp; Vulkan Runtimes</text:span></text:p>

      <text:p text:style-name="P_Subsection">Option B (Founding Systems Engineer / 0-to-1 Infrastructure):</text:p>
      <text:p text:style-name="P_Callout"><text:span text:style-name="T_Bold">Principal Systems Architect | Decoupling Monoliths, GPU Compute &amp; Zero-Copy Systems</text:span></text:p>

      <text:p text:style-name="P_Subsection">Option C (Spatial &amp; Physical Simulation):</text:p>
      <text:p text:style-name="P_Callout"><text:span text:style-name="T_Bold">Staff Systems Engineer | 3D Spatial Runtimes, Vulkan Raymarching &amp; Numerical Solvers</text:span></text:p>

      <!-- SECTION 2: ABOUT / BIO -->
      <text:p text:style-name="P_Section_Header">2. "ABOUT" / FOUNDER PITCH (BIO)</text:p>
      <text:p text:style-name="P_Body">Startup founders want to know what you can build autonomously without overhead or hand-holding:</text:p>

      <text:p text:style-name="P_Callout">
        I am a Systems Architect and Staff Engineer with 10+ years of experience engineering high-throughput computational engines, GPU visualization pipelines, and cross-platform desktop architectures.<text:line-break/><text:line-break/>
        At early-stage and high-growth companies, I help technical teams solve high-volume data bottlenecks where raw compute meets strict sub-millisecond latency budgets. I have led the structural decoupling of massive, multi-million-line legacy C++ monoliths into clean, modular, cloud-ready execution tiers across multiple major release cycles.<text:line-break/><text:line-break/>
        What I build &amp; deliver:<text:line-break/>
        • Low-Level Compute &amp; Graphics: Native C++20, NVIDIA CUDA, and Vulkan 1.3 shaders (single-pass 3D raymarching, 3D occupancy grid empty-space skipping, lock-free SPSC concurrency, and cache-line alignment).<text:line-break/>
        • Zero-Copy IPC &amp; Interop: Designing pybind11 in-process bridges and streaming WebSockets that eliminate hundreds of megabytes of serialization overhead between native solvers and Python/TypeScript web layers.<text:line-break/>
        • Enterprise Multi-Tenancy &amp; Security: PostgreSQL 18 Row-Level Security (FORCE RLS), transaction-local role switching (SET LOCAL), and automated DICOM PS3.15 de-identification pipelines.<text:line-break/>
        • Cross-Functional Autonomy: Defining technical RFCs, establishing multi-quarter engineering roadmaps, and unblocking engineering teams without administrative drag.<text:line-break/><text:line-break/>
        Looking to partner with ambitious teams building in Medical AI, Robotics &amp; Spatial Perception, Autonomous Systems, Simulation/Digital Twins, or High-Performance AI Infrastructure.
      </text:p>

      <!-- SECTION 3: WHAT I'M LOOKING FOR -->
      <text:p text:style-name="P_Section_Header">3. "WHAT I'M LOOKING FOR" SECTION</text:p>
      <text:p text:style-name="P_Body">Wellfound asks candidates what kind of culture, stage, and challenges they are seeking:</text:p>

      <text:p text:style-name="P_Callout">
        <text:span text:style-name="T_Bold">Desired Roles:</text:span> Principal Systems Architect, Staff Software Engineer (Systems / GPU), Founding Systems Engineer, Tech Lead Manager.<text:line-break/>
        <text:span text:style-name="T_Bold">Company Stage:</text:span> Series A through Series D, Growth, or Well-Funded Early-Stage with high technical complexity.<text:line-break/>
        <text:span text:style-name="T_Bold">Technical Focus:</text:span> High-Performance Computing (HPC), GPU Runtimes, Spatial Computing, 3D Graphics, Autonomous Systems, and AI Platform Infrastructure.<text:line-break/>
        <text:span text:style-name="T_Bold">Culture &amp; Team:</text:span> High-trust, low-bureaucracy engineering cultures that value rigorous systems craftsmanship, performance profiling, and direct technical ownership.
      </text:p>

      <!-- SECTION 4: FEATURED PROJECT -->
      <text:p text:style-name="P_Section_Header">4. WELLFOUND "FEATURED PROJECT" ENTRY</text:p>
      <text:p text:style-name="P_Body">Add under Wellfound’s portfolio / projects section:</text:p>

      <text:p text:style-name="P_Callout">
        <text:span text:style-name="T_Bold">Project Name:</text:span> Real-Time Spatial Data Processing &amp; 3D Analytics Workstation (MIVW)<text:line-break/>
        <text:span text:style-name="T_Bold">Repository Link:</text:span> <text:a xlink:href="https://github.com/mpg18031/medical-image-workstation" text:style-name="T_Link">https://github.com/mpg18031/medical-image-workstation</text:a><text:line-break/>
        <text:span text:style-name="T_Bold">Summary:</text:span> A production-grade blueprint for modernizing legacy desktop architectures into cross-platform execution tiers under strict sub-millisecond latency constraints.<text:line-break/><text:line-break/>
        <text:span text:style-name="T_Bold">Key Architectural Highlights:</text:span><text:line-break/>
        • Vulkan 1.3 single-pass 3D raymarching with 3D occupancy grid empty-space skipping (60+ FPS on 512³ volumes).<text:line-break/>
        • Zero-copy pybind11 ABI bridge eliminating 250MB+ serialization penalties between C++ and Python.<text:line-break/>
        • Lock-free SPSC ring buffer with alignas(64) cache-line padding to eliminate thread contention and false sharing.<text:line-break/>
        • Multi-tenant PostgreSQL 18 with FORCE Row-Level Security, transaction-scoped roles, and DICOM PS3.15 de-identification.<text:line-break/>
        • 52/52 passing CTest suite with perceptual image testing, Schemathesis fuzzing, and Playwright E2E.
      </text:p>

      <!-- SECTION 5: EXPERIENCE -->
      <text:p text:style-name="P_Section_Header">5. EXPERIENCE ENTRIES (WELLFOUND FORMAT)</text:p>

      <text:p text:style-name="P_Subsection">Role 1: R&amp;D Software Engineer, Staff | Company #3 / Company #2</text:p>
      <text:p text:style-name="P_Body"><text:span text:style-name="T_Bold">Dates:</text:span> Apr. 2020 – Present<text:line-break/>
      <text:span text:style-name="T_Bold">Description:</text:span> Technical lead responsible for core architecture, simulation performance, and modernization of enterprise-scale multi-domain physical system platforms (Twin Builder).</text:p>

      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Monolith Decoupling:</text:span> Architected the structural separation of a complex C++ desktop monolith into a clean, modular engine-and-service framework within 2 release cycles, enabling independent solver versioning and cross-platform execution.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Rendering Engine Optimization:</text:span> Re-engineered the Modelica schematic connection engine and diagram rendering pipeline, eliminating UI thread freezes when navigating complex multi-thousand-component layouts.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Cross-Platform Desktop Enablement:</text:span> Led the technical design of a next-generation Electron/Vue.js client replacing Windows-only legacy UI components with sandboxed, multi-platform execution.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Low-Latency Streaming:</text:span> Built native C++ to Python/Node.js IPC interfaces and WebSocket channels, cutting time-series telemetry transfer latency from multi-second batch delays to sub-millisecond updates.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Technical Leadership:</text:span> Steered multi-quarter architectural roadmaps, led technical RFC design reviews across engineering teams, and mentored senior engineers in modern C++ and GPU programming.</text:p>

      <text:p text:style-name="P_Subsection">Role 2: Software Development Engineer II | Company #2</text:p>
      <text:p text:style-name="P_Body"><text:span text:style-name="T_Bold">Dates:</text:span> Apr. 2015 – Apr. 2020<text:line-break/>
      <text:span text:style-name="T_Bold">Description:</text:span> Engineered core solver components, numerical algorithms, and diagram interfaces for industrial-grade system simulation software.</text:p>

      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Execution Engine Optimization:</text:span> Profiled and refactored core computational loops and memory access patterns in legacy C++, eliminating CPU bottlenecks and resolving production stability issues on large simulation workloads.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Extensible Plugin Architecture:</text:span> Designed standard dynamic linking layers that enabled external numerical solvers and third-party CAE libraries to interface directly into the simulation runtime.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Cross-Functional Delivery:</text:span> Partnered with product and solver teams to translate complex physical workflow requirements into modular software specifications, delivering algorithmic enhancements on schedule.</text:p>

      <!-- SECTION 6: FOUNDER OUTREACH NOTE -->
      <text:p text:style-name="P_Section_Header">6. FOUNDER / CTO OUTREACH MESSAGE TEMPLATE</text:p>
      <text:p text:style-name="P_Body">When applying directly to startup founders or CTOs on Wellfound, use this crisp 3-sentence note:</text:p>

      <text:p text:style-name="P_Callout">
        "Hi [Founder/CTO Name], I’ve spent the past 10 years engineering high-throughput C++ computational engines, real-time GPU visualization pipelines (CUDA, Vulkan), and modernizing complex desktop monoliths into cross-platform execution tiers. I was drawn to [Company Name]’s mission in [problem space] because it requires solving difficult compute and latency bottlenecks at scale. I recently published an open-source, hardware-accelerated spatial analytics workstation blueprint (MIVW) demonstrating zero-copy C++/Python interop and Vulkan raymarching (https://github.com/mpg18031/medical-image-workstation). I’d love to connect and discuss how I can help accelerate your systems architecture."
      </text:p>

    </office:text>
  </office:body>
</office:document-content>
"""


def generate_odt():
    print(f"Creating {ODT_FILENAME}...")
    with zipfile.ZipFile(ODT_FILENAME, "w") as zf:
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)
        zf.writestr(
            "META-INF/manifest.xml",
            MANIFEST_XML.strip(),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        zf.writestr("meta.xml", META_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr(
            "styles.xml", STYLES_XML.strip(), compress_type=zipfile.ZIP_DEFLATED
        )
        zf.writestr(
            "content.xml", CONTENT_XML.strip(), compress_type=zipfile.ZIP_DEFLATED
        )

    print(
        f"Successfully generated {ODT_FILENAME} ({os.path.getsize(ODT_FILENAME)} bytes)."
    )

    print("Converting to PDF...")
    res_pdf = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", ODT_FILENAME],
        capture_output=True,
        text=True,
    )
    if res_pdf.returncode == 0:
        print(
            f"Successfully generated {PDF_FILENAME} ({os.path.getsize(PDF_FILENAME)} bytes)."
        )
    else:
        print("PDF conversion failed:", res_pdf.stderr)


if __name__ == "__main__":
    generate_odt()
