#!/usr/bin/env python3
"""
Generate a professional, publication-quality OpenDocument Text (.odt) resume.
Uses standard library zipfile and generates ODF 1.2 compliant XML.
"""

import os
import zipfile

ODT_FILENAME = "Resume_Staff_Principal_Systems_Architect.odt"

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
    <dc:title>Resume - Staff / Principal Systems Architect</dc:title>
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
    <style:font-face style:name="Arial" svg:font-family="Arial, 'Liberation Sans', sans-serif"/>
  </office:font-face-decls>
  <office:styles>
    <style:default-style style:family="paragraph">
      <style:paragraph-properties fo:hyphenation-ladder-count="no-limit" fo:hyphenation-keep="auto"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="10pt" fo:color="#222222"/>
    </style:default-style>
  </office:styles>
  <office:automatic-styles>
    <style:page-layout style:name="pm1">
      <style:page-layout-properties fo:page-width="8.5in" fo:page-height="11in"
                                    fo:margin-top="0.5in" fo:margin-bottom="0.5in"
                                    fo:margin-left="0.55in" fo:margin-right="0.55in"/>
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
    <!-- Text Styles -->
    <style:style style:name="T_Bold" style:family="text">
      <style:text-properties fo:font-weight="bold"/>
    </style:style>
    <style:style style:name="T_Lead_Tag" style:family="text">
      <style:text-properties fo:font-weight="bold" fo:color="#1a365d"/>
    </style:style>
    <style:style style:name="T_Role_Title" style:family="text">
      <style:text-properties fo:font-weight="bold" fo:font-size="10.5pt" fo:color="#0f172a"/>
    </style:style>
    <style:style style:name="T_Company" style:family="text">
      <style:text-properties fo:font-weight="bold" fo:color="#334155"/>
    </style:style>
    <style:style style:name="T_Dates" style:family="text">
      <style:text-properties fo:font-style="italic" fo:color="#475569"/>
    </style:style>
    <style:style style:name="T_Subheading" style:family="text">
      <style:text-properties fo:font-size="9.5pt" fo:color="#475569"/>
    </style:style>
    <style:style style:name="T_Link" style:family="text">
      <style:text-properties fo:color="#1d4ed8" fo:text-decoration="underline"/>
    </style:style>

    <!-- Paragraph Styles -->
    <style:style style:name="P_Name" style:family="paragraph">
      <style:paragraph-properties fo:text-align="center" fo:margin-top="0pt" fo:margin-bottom="1pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="19pt" fo:font-weight="bold" fo:color="#0f172a" fo:letter-spacing="0.5pt"/>
    </style:style>

    <style:style style:name="P_Contact" style:family="paragraph">
      <style:paragraph-properties fo:text-align="center" fo:margin-top="0pt" fo:margin-bottom="3pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9pt" fo:color="#475569"/>
    </style:style>

    <style:style style:name="P_Headline" style:family="paragraph">
      <style:paragraph-properties fo:text-align="center" fo:margin-top="0pt" fo:margin-bottom="6pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="11pt" fo:font-weight="bold" fo:color="#1e3a8a"/>
    </style:style>

    <style:style style:name="P_Section_Header" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="8pt" fo:margin-bottom="3pt" fo:keep-with-next="always"
                                  fo:border-bottom="1.2pt solid #1e3a8a" fo:padding-bottom="1.5pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="10.5pt" fo:font-weight="bold" fo:color="#1e3a8a" fo:letter-spacing="0.5pt"/>
    </style:style>

    <style:style style:name="P_Summary" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="2pt" fo:margin-bottom="4pt" fo:line-height="115%"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9.5pt" fo:color="#1e293b"/>
    </style:style>

    <style:style style:name="P_Job_Header" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="5pt" fo:margin-bottom="1pt" fo:keep-with-next="always"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="10pt"/>
    </style:style>

    <style:style style:name="P_Job_Scope" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="0pt" fo:margin-bottom="2pt" fo:line-height="110%"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9pt" fo:font-style="italic" fo:color="#334155"/>
    </style:style>

    <style:style style:name="P_Bullet" style:family="paragraph">
      <style:paragraph-properties fo:margin-left="0.22in" fo:text-indent="-0.22in"
                                  fo:margin-top="1.5pt" fo:margin-bottom="2pt" fo:line-height="115%"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9.3pt" fo:color="#1e293b"/>
    </style:style>

    <style:style style:name="P_Skill_Line" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="1.5pt" fo:margin-bottom="2pt" fo:line-height="115%"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9.3pt" fo:color="#1e293b"/>
    </style:style>

    <style:style style:name="P_Edu" style:family="paragraph">
      <style:paragraph-properties fo:margin-top="2pt" fo:margin-bottom="2pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="9.5pt" fo:color="#1e293b"/>
    </style:style>
  </office:automatic-styles>

  <office:body>
    <office:text>
      <!-- HEADER -->
      <text:p text:style-name="P_Name">MY NAME</text:p>
      <text:p text:style-name="P_Contact">Pittsburgh, PA | 123-223-2233 | no_email@outlook.com</text:p>
      <text:p text:style-name="P_Headline">STAFF / PRINCIPAL SYSTEMS ARCHITECT — COMPUTATIONAL ENGINES &amp; GPU RUNTIMES</text:p>

      <!-- SUMMARY -->
      <text:p text:style-name="P_Section_Header">EXECUTIVE SUMMARY</text:p>
      <text:p text:style-name="P_Summary">High-Performance Systems Architect and Staff Software Engineer with 10+ years of experience engineering computational engines, real-time visualization pipelines, and cross-platform desktop architectures. Proven track record modernizing complex legacy C++ desktop monoliths into decoupled, high-performance systems while establishing technical roadmaps across multi-quarter releases. Recognized for bridging hardware-accelerated compute kernels (CUDA, Vulkan, C++20) with distributed analytical platforms, driving cross-functional technical consensus, and mentoring senior engineering talent.</text:p>

      <!-- SKILLS -->
      <text:p text:style-name="P_Section_Header">CORE COMPETENCIES &amp; TECHNICAL STACK</text:p>
      <text:p text:style-name="P_Skill_Line">• <text:span text:style-name="T_Bold">Systems, HPC &amp; GPU:</text:span> C++20/23, NVIDIA CUDA, Vulkan 1.3 (Compute/Raymarching SPIR-V Shaders), SIMD, Multi-threading, Lock-Free Concurrency (SPSC Ring Buffers), Memory Profiling (AddressSanitizer, Valgrind).</text:p>
      <text:p text:style-name="P_Skill_Line">• <text:span text:style-name="T_Bold">Architecture &amp; Runtimes:</text:span> pybind11 Zero-Copy Interop, Monolith Modernization, AST &amp; Symbolic Solvers (Modelica), Low-Latency IPC, mTLS, Electron Shell Hardening, Linux/Windows Systems.</text:p>
      <text:p text:style-name="P_Skill_Line">• <text:span text:style-name="T_Bold">Web, Services &amp; API:</text:span> Python 3.12 (FastAPI, AsyncIO), TypeScript, Vue 3 / Quasar, WebSockets, RESTful Architecture, Docker/Compose.</text:p>
      <text:p text:style-name="P_Skill_Line">• <text:span text:style-name="T_Bold">Data Infrastructure &amp; Security:</text:span> PostgreSQL 18 (Row-Level Security, pgcrypto), TimescaleDB, S3/MinIO Content-Addressed Storage, DICOM PS3.15 De-Identification.</text:p>

      <!-- FEATURED PROJECT -->
      <text:p text:style-name="P_Section_Header">FEATURED SYSTEMS PROJECT</text:p>
      <text:p text:style-name="P_Job_Header">
        <text:span text:style-name="T_Role_Title">Real-Time Spatial Data Processing &amp; 3D Analytics Workstation (MIVW)</text:span> | <text:span text:style-name="T_Company">Architect &amp; Lead Developer</text:span>
      </text:p>
      <text:p text:style-name="P_Job_Scope">GitHub: <text:a xlink:href="https://github.com/mpg18031/medical-image-workstation" text:style-name="T_Link">https://github.com/mpg18031/medical-image-workstation</text:a> — Engineered an end-to-end, hardware-accelerated workstation to ingest, process, and render multi-gigabyte spatial volumes under interactive sub-millisecond latency constraints.</text:p>

      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Hardware-Accelerated 3D Raymarching:</text:span> Designed a custom single-pass Vulkan 1.3 volume raymarching pipeline with 3D occupancy grid acceleration for empty-space skipping, delivering deterministic 60+ FPS rendering of 512³ spatial datasets.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Zero-Copy Interop &amp; Low-Latency IPC:</text:span> Architected an in-process Python/C++ boundary using pybind11 and explicit gil_scoped_release guards, eliminating 250MB+ per-volume serialization penalties and cutting data transfer latency to zero-copy memory views.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Lock-Free Concurrency &amp; Memory Layout:</text:span> Implemented an asynchronous SPSC ring buffer with alignas(64) cache-line padding to eliminate CPU core false sharing and thread contention on high-frequency streaming paths.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Multi-Tenant Security &amp; Healthcare Compliance:</text:span> Built a zero-leak PostgreSQL 18 data tier enforcing strict Row-Level Security (FORCE RLS) with transaction-scoped role isolation (SET LOCAL), column-level encryption, and automated DICOM PS3.15 de-identification with burned-in annotation hazard detection.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">End-to-End Verification &amp; Fuzzing:</text:span> Instituted a comprehensive test pyramid including GoogleTest/CTest with perceptual golden-image diffs (SSIM/PSNR), Schemathesis contract fuzzing, and Playwright E2E suites driving the packaged Electron desktop client.</text:p>

      <!-- EXPERIENCE -->
      <text:p text:style-name="P_Section_Header">PROFESSIONAL EXPERIENCE</text:p>

      <text:p text:style-name="P_Job_Header">
        <text:span text:style-name="T_Role_Title">R&amp;D Software Engineer, Staff</text:span> | <text:span text:style-name="T_Company">Company #3 / Company #2</text:span> | <text:span text:style-name="T_Dates">Apr. 2020 – Present</text:span>
      </text:p>
      <text:p text:style-name="P_Job_Scope">Technical lead responsible for core architecture, simulation performance, and modernization of enterprise-scale multi-domain physical system platforms (Twin Builder).</text:p>

      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Monolith Modernization &amp; Decoupling:</text:span> Architected the structural extraction of a tangled legacy C++ desktop monolith into a clean, modular engine-and-service architecture within 2 release cycles, enabling independent compute versioning and unblocking web/cross-platform initiatives.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Graphical Engine Optimization:</text:span> Re-engineered the Modelica schematic connection engine and diagram rendering pipeline, eliminating visual performance bottlenecks and unlocking seamless real-time manipulation of complex multi-thousand-component system models.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Cross-Platform Desktop Enablement:</text:span> Led the technical design of the next-generation Electron/Vue.js desktop client to replace Windows-only legacy UI components, achieving full feature parity, sandboxed security boundaries, and consistent Linux/Windows execution.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Computational Interop &amp; Streaming:</text:span> Developed native C++ to Python/Node.js IPC interfaces and WebSocket streaming channels, reducing time-series telemetry transfer latency from multi-second batch delays to sub-millisecond updates.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Technical Leadership &amp; Execution Governance:</text:span> Steered multi-quarter architectural roadmaps, led technical design reviews across engineering teams, authored engineering RFCs, and mentored senior engineers in high-performance C++ and GPU programming practices.</text:p>

      <text:p text:style-name="P_Job_Header">
        <text:span text:style-name="T_Role_Title">Software Development Engineer II</text:span> | <text:span text:style-name="T_Company">Company #2</text:span> | <text:span text:style-name="T_Dates">Apr. 2015 – Apr. 2020</text:span>
      </text:p>
      <text:p text:style-name="P_Job_Scope">Engineered core solver components, numerical algorithms, and diagram interfaces for industrial-grade system simulation software.</text:p>

      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Execution Engine Optimization:</text:span> Profiled and refactored core computational loops and memory access patterns in legacy C++, eliminating CPU bottlenecks and resolving production stability issues on large simulation workloads.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Third-Party Extensibility Architecture:</text:span> Designed standard plugin interfaces and dynamic linking layers that allowed external solvers and third-party CAE libraries to integrate directly into the simulation runtime.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Lead_Tag">Cross-Functional Delivery:</text:span> Partnered with product management and solver teams to translate customer workflow requirements into modular software specifications, consistently delivering complex algorithmic enhancements on schedule across major releases.</text:p>

      <!-- EDUCATION -->
      <text:p text:style-name="P_Section_Header">EDUCATION</text:p>
      <text:p text:style-name="P_Edu">
        <text:span text:style-name="T_Bold">Master of Science in Computer Science (Data Communications &amp; Distributed Systems)</text:span><text:line-break/>
        State University of New York (SUNY) at Binghamton, NY, USA
      </text:p>
      <text:p text:style-name="P_Edu">
        <text:span text:style-name="T_Bold">Bachelor of Science in Computer Science (Automation &amp; Industrial Informatics)</text:span><text:line-break/>
        “Lower Danube” University, Galați, Romania
      </text:p>

    </office:text>
  </office:body>
</office:document-content>
"""


def generate_odt():
    print(f"Creating {ODT_FILENAME}...")
    with zipfile.ZipFile(ODT_FILENAME, "w") as zf:
        # mimetype must be the first file and uncompressed (ZIP_STORED)
        zf.writestr("mimetype", MIMETYPE, compress_type=zipfile.ZIP_STORED)

        # Manifest
        zf.writestr(
            "META-INF/manifest.xml",
            MANIFEST_XML.strip(),
            compress_type=zipfile.ZIP_DEFLATED,
        )

        # Meta, Styles, Content
        zf.writestr("meta.xml", META_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("styles.xml", STYLES_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("content.xml", CONTENT_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)

    print(f"Successfully generated {ODT_FILENAME} ({os.path.getsize(ODT_FILENAME)} bytes).")


if __name__ == "__main__":
    generate_odt()
