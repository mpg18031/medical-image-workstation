#!/usr/bin/env python3
"""
Generate a professional, copy-paste-ready OpenDocument Text (.odt) for LinkedIn Profile Optimization.
Includes Headline, About Section, Experience, Featured Project, and Core Skills for ATS & Recruiter Search.
"""

import os
import zipfile

ODT_FILENAME = "LinkedIn_Profile_Staff_Principal_Systems_Architect.odt"

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
    <dc:title>LinkedIn Profile Optimization - Staff / Principal Systems Architect</dc:title>
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
      <style:text-properties fo:font-weight="bold" fo:color="#0f766e"/>
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
                                  fo:border-bottom="1.5pt solid #0f766e" fo:padding-bottom="2pt"/>
      <style:text-properties style:font-name="Calibri" fo:font-size="12pt" fo:font-weight="bold" fo:color="#0f766e" fo:letter-spacing="0.5pt"/>
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
                                  fo:background-color="#f8fafc" fo:padding="6pt"
                                  fo:border-left="3pt solid #0f766e"/>
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
      <text:p text:style-name="P_Doc_Title">LINKEDIN PROFILE OPTIMIZATION GUIDE</text:p>
      <text:p text:style-name="P_Doc_Subtitle">Copy-paste ready headlines, about narrative, experience bullets, and featured project calibrated for Staff/Principal Systems Architect &amp; Engineering Leadership roles.</text:p>

      <!-- SECTION 1: HEADLINES -->
      <text:p text:style-name="P_Section_Header">1. LINKEDIN HEADLINE (MAX 220 CHARACTERS)</text:p>
      <text:p text:style-name="P_Body">Your headline is the single highest-weighted field in LinkedIn Recruiter search algorithms. Below is the primary recommendation, followed by two targeted variations depending on your search focus:</text:p>

      <text:p text:style-name="P_Subsection">Option A (Recommended — High-Impact Principal Systems &amp; GPU Focus):</text:p>
      <text:p text:style-name="P_Callout"><text:span text:style-name="T_Bold">Staff / Principal Systems Architect | High-Performance Computing, GPU Runtimes &amp; Computational Engines (C++20, CUDA, Vulkan) | Legacy Monolith Modernization &amp; Distributed Systems</text:span></text:p>

      <text:p text:style-name="P_Subsection">Option B (Simulation R&amp;D &amp; Physical Modeling Leadership):</text:p>
      <text:p text:style-name="P_Callout"><text:span text:style-name="T_Bold">Staff Software Engineer &amp; Systems Architect | Simulation Platforms (Modelica) &amp; Real-Time Graphics | C++20, CUDA, Vulkan, Zero-Copy IPC | Technical Roadmaps &amp; Engineering Stewardship</text:span></text:p>

      <text:p text:style-name="P_Subsection">Option C (Tech Lead Manager / Systems Leadership):</text:p>
      <text:p text:style-name="P_Callout"><text:span text:style-name="T_Bold">Staff Systems Architect &amp; Technical Lead | High-Performance Engines, GPU Acceleration &amp; Cross-Platform Desktop | Leading Architecture, Technical RFCs &amp; Multi-Quarter Execution</text:span></text:p>

      <!-- SECTION 2: ABOUT SECTION -->
      <text:p text:style-name="P_Section_Header">2. "ABOUT" SECTION</text:p>
      <text:p text:style-name="P_Body">Formatted in first-person narrative with clean spacing, bulleted domain pillars, and strategic keyword indexing at the bottom:</text:p>

      <text:p text:style-name="P_Callout">
        I am a Systems Architect and Staff Software Engineer with over a decade of experience designing high-throughput computational engines, real-time visualization pipelines, and cross-platform desktop architectures.<text:line-break/><text:line-break/>
        My engineering focus centers on solving complex computational bottlenecks where high-volume spatial or physical data meets interactive execution limits. Throughout my career, I have specialized in untangling and modernizing multi-million-line legacy C++ desktop monoliths into clean, decoupled, high-performance engines capable of powering next-generation web, cloud, and desktop platforms.<text:line-break/><text:line-break/>
        What I bring to engineering organizations:<text:line-break/>
        • Systems &amp; GPU Architecture: Deep expertise in C++20, CUDA, and Vulkan 1.3 shaders (single-pass raymarching, 3D occupancy grids, empty-space skipping, lock-free SPSC ring buffers, and cache-line alignment).<text:line-break/>
        • Zero-Copy Interop &amp; Runtimes: Designing high-velocity in-process ABI bridges (pybind11) and low-latency streaming protocols that eliminate multi-megabyte serialization penalties across language boundaries.<text:line-break/>
        • Monolith Modernization: A proven methodology for structurally isolating core mathematical solvers from presentation layers across multi-quarter release cycles without regressing system stability.<text:line-break/>
        • Technical Stewardship &amp; Mentorship: Leading technical RFC reviews, aligning multi-team architectural roadmaps, and mentoring senior engineers in modern systems programming and memory safety.<text:line-break/><text:line-break/>
        I am energized by mission-critical engineering problems in high-performance computing, spatial computing, simulation compilers, and real-time visualization platforms.<text:line-break/><text:line-break/>
        Technical Specialties:<text:line-break/>
        C++20/23 | NVIDIA CUDA | Vulkan 1.3 | SIMD &amp; Lock-Free Concurrency | pybind11 Zero-Copy | Python 3.12 (FastAPI, AsyncIO) | Modelica &amp; AST Solvers | Electron &amp; Vue.js | PostgreSQL 18 (RLS) | TimescaleDB | Docker | High-Throughput Streaming Runtimes
      </text:p>

      <!-- SECTION 3: EXPERIENCE -->
      <text:p text:style-name="P_Section_Header">3. EXPERIENCE / WORK HISTORY</text:p>

      <text:p text:style-name="P_Subsection">Role 1: R&amp;D Software Engineer, Staff | Company #3 / Company #2</text:p>
      <text:p text:style-name="P_Body"><text:span text:style-name="T_Bold">Dates:</text:span> Apr. 2020 – Present<text:line-break/>
      <text:span text:style-name="T_Bold">Role Context:</text:span> Technical lead responsible for core architecture, simulation performance, and modernization of enterprise-scale multi-domain physical system platforms (Twin Builder).</text:p>

      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Monolith Modernization &amp; Decoupling:</text:span> Architected the structural extraction of a tangled legacy C++ desktop monolith into a clean, modular engine-and-service architecture within 2 release cycles, enabling independent compute versioning and unblocking web/cross-platform initiatives.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Graphical Engine Optimization:</text:span> Re-engineered the Modelica schematic connection engine and diagram rendering pipeline, eliminating visual performance bottlenecks and unlocking seamless real-time manipulation of complex multi-thousand-component system models.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Cross-Platform Desktop Enablement:</text:span> Led the technical design of the next-generation Electron/Vue.js desktop client to replace Windows-only legacy UI components, achieving full feature parity, sandboxed security boundaries, and consistent Linux/Windows execution.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Computational Interop &amp; Streaming:</text:span> Developed native C++ to Python/Node.js IPC interfaces and WebSocket streaming channels, reducing time-series telemetry transfer latency from multi-second batch delays to sub-millisecond updates.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Technical Leadership &amp; Execution Governance:</text:span> Steered multi-quarter architectural roadmaps, led technical design reviews across engineering teams, authored engineering RFCs, and mentored senior engineers in high-performance C++ and GPU programming practices.</text:p>
      <text:p text:style-name="P_TechTags">Skills: C++20 · High-Performance Computing (HPC) · Software Architecture · System Simulation · Modelica · Vulkan · Python · Electron.js · Monolith Modernization · Technical Leadership</text:p>

      <text:p text:style-name="P_Subsection">Role 2: Software Development Engineer II | Company #2</text:p>
      <text:p text:style-name="P_Body"><text:span text:style-name="T_Bold">Dates:</text:span> Apr. 2015 – Apr. 2020<text:line-break/>
      <text:span text:style-name="T_Bold">Role Context:</text:span> Engineered core solver components, numerical algorithms, and diagram interfaces for industrial-grade system simulation software.</text:p>

      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Execution Engine Optimization:</text:span> Profiled and refactored core computational loops and memory access patterns in legacy C++, eliminating CPU bottlenecks and resolving production stability issues on large simulation workloads.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Third-Party Extensibility Architecture:</text:span> Designed standard plugin interfaces and dynamic linking layers that allowed external solvers and third-party CAE libraries to integrate directly into the simulation runtime.</text:p>
      <text:p text:style-name="P_Bullet">• <text:span text:style-name="T_Tag">Cross-Functional Delivery:</text:span> Partnered with product management and solver teams to translate customer workflow requirements into modular software specifications, consistently delivering complex algorithmic enhancements on schedule across major releases.</text:p>
      <text:p text:style-name="P_TechTags">Skills: C++ · Algorithm Optimization · Multi-threading · Software Extensibility · Simulation Software · Object-Oriented Design (OOD)</text:p>

      <!-- SECTION 4: FEATURED PROJECT -->
      <text:p text:style-name="P_Section_Header">4. LINKEDIN "FEATURED" SECTION ENTRY</text:p>
      <text:p text:style-name="P_Body">Add this entry under your LinkedIn "Featured" section (Media / Link):</text:p>

      <text:p text:style-name="P_Callout">
        <text:span text:style-name="T_Bold">Title:</text:span> Real-Time Spatial Data Processing &amp; 3D Analytics Workstation (MIVW)<text:line-break/>
        <text:span text:style-name="T_Bold">Link:</text:span> <text:a xlink:href="https://github.com/mpg18031/medical-image-workstation" text:style-name="T_Link">https://github.com/mpg18031/medical-image-workstation</text:a><text:line-break/>
        <text:span text:style-name="T_Bold">Description:</text:span> A production-grade blueprint for modernizing legacy desktop architectures into cross-platform execution tiers under strict sub-millisecond latency constraints. Features single-pass Vulkan 1.3 raymarching with 3D occupancy grid empty-space skipping, lock-free SPSC concurrency (alignas(64)), zero-copy pybind11 in-process bridges, and PostgreSQL 18 Row-Level Security.
      </text:p>

      <!-- SECTION 5: TOP SKILLS -->
      <text:p text:style-name="P_Section_Header">5. TOP 20 LINKEDIN SKILLS (ALIGNED TO RECRUITER SEARCH QUERIES)</text:p>
      <text:p text:style-name="P_Body">Make sure these exact skills are added to your profile (pinned top 5 in bold):</text:p>
      <text:p text:style-name="P_Bullet">1. <text:span text:style-name="T_Bold">High-Performance Computing (HPC)</text:span> (Pinned)</text:p>
      <text:p text:style-name="P_Bullet">2. <text:span text:style-name="T_Bold">C++ (C++20/C++23)</text:span> (Pinned)</text:p>
      <text:p text:style-name="P_Bullet">3. <text:span text:style-name="T_Bold">Software Architecture</text:span> (Pinned)</text:p>
      <text:p text:style-name="P_Bullet">4. <text:span text:style-name="T_Bold">GPU Computing (NVIDIA CUDA / Vulkan)</text:span> (Pinned)</text:p>
      <text:p text:style-name="P_Bullet">5. <text:span text:style-name="T_Bold">Distributed Systems</text:span> (Pinned)</text:p>
      <text:p text:style-name="P_Bullet">6. Computer Graphics (Vulkan / Shaders)</text:p>
      <text:p text:style-name="P_Bullet">7. Low Latency Architecture</text:p>
      <text:p text:style-name="P_Bullet">8. Multithreading &amp; Concurrency</text:p>
      <text:p text:style-name="P_Bullet">9. Monolith Modernization</text:p>
      <text:p text:style-name="P_Bullet">10. Modelica / System Simulation</text:p>
      <text:p text:style-name="P_Bullet">11. Python (FastAPI / AsyncIO)</text:p>
      <text:p text:style-name="P_Bullet">12. pybind11 / Zero-Copy Interop</text:p>
      <text:p text:style-name="P_Bullet">13. Electron.js / Desktop Architecture</text:p>
      <text:p text:style-name="P_Bullet">14. TypeScript &amp; Vue.js</text:p>
      <text:p text:style-name="P_Bullet">15. PostgreSQL / Database Architecture</text:p>
      <text:p text:style-name="P_Bullet">16. Performance Profiling &amp; Optimization</text:p>
      <text:p text:style-name="P_Bullet">17. Technical Leadership</text:p>
      <text:p text:style-name="P_Bullet">18. Cross-Functional Team Leadership</text:p>
      <text:p text:style-name="P_Bullet">19. Docker &amp; Containerization</text:p>
      <text:p text:style-name="P_Bullet">20. TimescaleDB</text:p>

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
        zf.writestr("styles.xml", STYLES_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("content.xml", CONTENT_XML.strip(), compress_type=zipfile.ZIP_DEFLATED)

    print(f"Successfully generated {ODT_FILENAME} ({os.path.getsize(ODT_FILENAME)} bytes).")


if __name__ == "__main__":
    generate_odt()
