# Security Policy

## Supported Versions

We recommend always using the latest released version of `mycat`.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

## Reporting a Vulnerability

Security issues are taken seriously. If you discover a potential security vulnerability—especially regarding API key storage, process execution, or clipboard/input handling:

1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately via **GitHub Security Advisories** on the repository page:
   - Navigate to the **Security** tab of the repository.
   - Click on **Advisories** and select **Report a vulnerability**.
3. Alternatively, contact the repository maintainers directly.

### What to include in your report

Please include as much detail as possible to help us reproduce and resolve the issue quickly:
- Description of the vulnerability and its potential impact.
- Step-by-step instructions or proof-of-concept (PoC) to reproduce the vulnerability.
- Operating system and version.
- Python version and installed package versions (`pip list`).
- Any suggested remediations or mitigations.

### Response Timeline

- **Acknowledgment**: You can expect an initial acknowledgment within 48 hours.
- **Assessment**: We will investigate and provide an assessment and timeline for a patch.
- **Fix & Release**: Once a patch is developed and verified, a new release will be published along with appropriate security disclosure notes.
