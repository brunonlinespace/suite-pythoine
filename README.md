<p align="center">
  <a href="https://github.com/brunonlinespace/suite-pythoine">
    <img
      src="suite_pythoine/assets/suite-pythoine-master-1024.png"
      alt="Suite Pythoine"
      width="280"
    >
  </a>
</p>

<h1 align="center">Suite Pythoine</h1>

<p align="center">
  <strong>Your applications. Your files. One home.</strong>
</p>

<p align="center">
  <strong>Friendly. Fast. Focused.</strong>
</p>

<p align="center">
  <a href="https://github.com/brunonlinespace/suite-pythoine">
    github.com/brunonlinespace/suite-pythoine
  </a>
</p>

Suite Pythoine is a desktop application hub for the **brunonlinespace**
software family.

It brings together focused standalone applications, richer workspace
editions, portable and managed installations, file routing, component
discovery, and application management in one consistent interface.

The individual applications remain useful on their own. Suite Pythoine
simply gives them a shared home.

---

## What is Suite Pythoine?

Suite Pythoine is designed around a simple idea:

> **Small applications should remain small applications — but they should
> still work beautifully together.**

Rather than turning every tool into one enormous program, Suite Pythoine
provides the common infrastructure around them:

- discover installed applications
- install supported components
- launch applications
- manage multiple installed versions
- open files with the appropriate application
- remember preferred file routes
- support portable and managed workflows
- expose application metadata and capabilities
- keep the component catalogue independently updateable

Applications remain free to run independently outside the Suite.

---

# Featured applications

## Markopad & Marko Plus

### Markopad

A focused Markdown editor built around a clean writing workflow.

**Markopad** keeps Markdown editing straightforward while providing the
tools needed to write, structure and preview documents without turning
the editor into an IDE.

**Focused Markdown. Clear workflow.**

### Marko Plus

**Marko Plus** takes the Markopad editing experience and adds the shared
Plus workspace infrastructure.

It combines:

- project and workspace management
- file and folder discovery
- a persistent project sidebar
- quick project selection
- richer document navigation
- **Edit**
- **Split View**
- **Preview**

Markopad remains the focused standalone editor.

Marko Plus is the workspace edition.

---

## Ricopad & Rico Plus

### Ricopad

A dedicated rich-text editor focused on **RTF**.

Ricopad provides a native document-editing environment with formatting,
lists, tables, colours, fonts, printing and persistent RTF structure.

It is deliberately a specialist editor rather than a general-purpose
office suite.

### Rico Plus

**Rico Plus** applies the same Plus workspace philosophy used by
Marko Plus to Ricopad.

It combines Ricopad's rich-text engine with the shared project and
workspace infrastructure descended from Python Lair.

**Ricopad for the document.  
Rico Plus for the workspace.**

---

## Nuxpad

Nuxpad is one of the foundational applications in the brunonlinespace
family.

Its development helped establish ideas that later evolved through
**Python Lair**, the Pad family and eventually the shared Plus workspace
architecture.

Nuxpad represents the lightweight-editor roots of the ecosystem:
focused tools, restrained interfaces and minimal friction between
opening a file and working on it.

---

## Python Lair

Python Lair occupies a special place in the history of the project
family.

The development path broadly became:

```text
Nuxpad
   ↓
Python Lair
   ↓
shared application/editor ideas
   ↓
Pad family
   ↓
extracted workspace scaffolding
   ↓
Marko Plus / Rico Plus
````

Python Lair therefore remains both a Python-focused working environment
and an architectural ancestor of the modern **Plus** applications.

---

## Timblee Pad

A specialist editor for web-oriented source files.

Timblee Pad concentrates on formats such as:

* HTML
* HTM
* CSS

It follows the same principle as the other Pads: give a particular kind
of file a focused application instead of making every editor responsible
for everything.

---

## Portapad

A lightweight PDF reader built around reading rather than
document-authoring complexity.

Portapad has evolved through experiments with:

* single-page reading
* continuous reading
* document contents
* search
* navigation

Its goal remains straightforward: make opening and reading a PDF quick
and comfortable.

---

## Beespector family

The **Beespector** family explores another branch of the same design
philosophy: inspection, browsing and organisation through focused
desktop interfaces.

### Beespector

The fuller inspection-oriented application.

### Beespector Lite

A lighter companion for users who want the essential workflow with less
surrounding machinery.

Both retain the brunonlinespace preference for applications that remain
understandable, portable and useful without requiring an enormous
software platform around them.

---

# Pads, Plus and Lair

The names describe different application roles.

| Family    | Meaning                                                      |
| --------- | ------------------------------------------------------------ |
| **Pad**   | A focused standalone application                             |
| **Plus**  | A Pad expanded with shared project/workspace infrastructure  |
| **Lair**  | The original workspace lineage represented by Python Lair    |
| **Suite** | The hub connecting and managing the wider application family |

The distinction is intentional.

A Plus application does not replace its Pad counterpart.

```text
Markopad   → focused Markdown editor
Marko Plus → Markdown workspace

Ricopad    → focused RTF editor
Rico Plus  → rich-text workspace
```

Users can choose whichever level of application they actually need.

---

# More of the ecosystem

Suite Pythoine is designed to accommodate a growing collection of
specialist applications and families.

Other projects include tools for:

* bookmark inspection and cleanup
* file management
* EPUB reading
* Git workflows
* website crawling and downloading
* media downloading
* development environments
* Linux system inspection

The ecosystem continues to favour **specialist applications over one
giant application**.

---

## Store Pythoine

**Store Pythoine** is the catalogue and software-distribution companion
to Suite Pythoine.

It provides a natural home for discovering supported applications and
complements Suite Pythoine's installation and component-management
infrastructure.

```text
Store Pythoine
      ↓
discover / obtain applications

Suite Pythoine
      ↓
install / manage / launch / route files
```

---

## LinSpectacles

The Linux inspection family is developed as its own distinct project
family while remaining compatible with the wider Pythoine ecosystem.

**LinSpectacles**

> **Expose. Explore. Explain.**

LinSpectacles consists of specialist Linux inspection tools and applets
designed around focused sources and focused outputs.

The family can remain independently developed and distributed while
Suite Pythoine provides a bridge for discovery, installation and
launching.

---

# File routing

Suite Pythoine can route supported files to applications that understand
them.

The component catalogue describes application capabilities rather than
forcing Suite Pythoine itself to understand every editor internally.

This allows components to evolve independently.

For example:

```text
.md / .markdown
        ↓
     Markopad

.rtf
        ↓
      Ricopad

.html / .htm / .css
        ↓
    Timblee Pad
```

Users can also retain preferred routes where multiple applications
support the same kind of file.

---

# Component catalogue

Suite Pythoine uses a trusted component catalogue to describe supported
applications.

The catalogue can contain information such as:

* component identity
* display name
* publisher
* supported formats
* capabilities
* installation sources
* repositories
* available versions
* routing information

Catalogue revisions can evolve independently of the main Suite
executable.

That means adding or updating supported software does not necessarily
require rebuilding the entire Hub.

---

# Portable and managed applications

One of the central goals of Suite Pythoine is to support more than one
way of running software.

Depending on the component, applications may be available as:

* source distributions
* portable applications
* AppImages
* managed installations

A standalone application should not have to surrender its independence
simply because it can also be managed by Suite Pythoine.

---

# Design philosophy

The brunonlinespace applications share a few recurring ideas.

### Focused applications

A program should have a clear purpose.

If two jobs make more sense as two applications, they do not need to be
forced together.

### Consistency without sameness

Applications share familiar conventions, workflows and visual language
where appropriate, while preserving the controls needed by their
particular document type or task.

### Standalone first

Applications should remain genuinely usable independently.

Suite integration is an enhancement, not a dependency.

### Portable where practical

Being able to carry an application, run another version alongside the
current one, or avoid unnecessary installation is treated as a useful
capability rather than an afterthought.

### Friendly. Fast. Focused.

The software should be approachable, responsive and concentrated on the
job in front of the user.

---

# A family, not a monolith

Suite Pythoine is intentionally **not** an attempt to merge every
brunonlinespace application into a single executable.

Instead:

```text
                    Suite Pythoine
                          │
          ┌───────────────┼───────────────┐
          │               │               │
        Pads            Plus          other families
          │               │               │
   focused apps     workspaces      specialist tools
          │               │               │
          └───────────────┴───────────────┘
                          │
                    shared ecosystem
```

The applications can evolve independently while still benefiting from
common discovery, routing and management infrastructure.

---

# Project status

Suite Pythoine is under active development.

Interfaces, catalogue capabilities and component support continue to
evolve as the wider application family grows.

The project favours deliberate incremental development over attempting
to turn the Suite into an all-purpose desktop environment.

---

# Repository

**Suite Pythoine**

[https://github.com/brunonlinespace/suite-pythoine](https://github.com/brunonlinespace/suite-pythoine)

---

# Author

**brunonlinespace**

Suite Pythoine and the surrounding software family are independent
open-source projects created under the brunonlinespace identity.

---

# License

See the `LICENSE` file included with the source distribution for the
licence applicable to this repository.

Individual applications distributed through or recognised by
Suite Pythoine may have their own licensing information and remain
independently maintained projects.

---

<p align="center">
  <strong>Suite Pythoine</strong><br>
  Friendly. Fast. Focused.
</p>
