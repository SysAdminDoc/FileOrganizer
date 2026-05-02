# Security Policy

## Supported Versions

- **Current**: v8.4.0+ (active development)
- **LTS**: v8.0.0–v8.3.x (security updates only)
- **EOL**: v7.x and earlier (no longer supported)

## Vulnerability Reporting

To report a vulnerability responsibly, email **security@example.com** with:
- Affected version(s)
- Impact (data loss, crash, RCE, etc.)
- Steps to reproduce
- Suggested mitigation

Do NOT file public issues for security bugs.

---

## Known Mitigations

### GHSA-24p2-j2jr-386w: psd-tools ZIP-bomb + integer overflow (CVE-pending)

**Impact**: High (DoS / OOM crash)  
**Severity**: CVSS 6.8

**Affected versions**: All with psd-tools support before v8.4.0

**Root cause**: Three vulnerabilities in `psd-tools.compression`:
1. `zlib.decompress()` called with no `max_length` → ZIP-bomb OOM crash
2. Width/height/depth never validated before buffer allocation (PSB allows 300K×300K px = 144 TB allocation)
3. `assert` statements used as runtime guards (silently disabled under `python -O`)

**Mitigation (v8.4.0+)**:
- Pre-parse PSD/PSB headers (bytes 0–26) before invoking `psd-tools`
- Reject files with width > 30,000 or height > 30,000 px (normal creative assets never exceed this)
- Verify PSD signature ("8BPS") before parsing
- Use `safe_psd_open()` wrapper (size guard + exception isolation)
- Pin `psd-tools>=2.0.0` (awaiting upstream fix; N-13 subprocess isolation available as fallback)

**Files changed**:
- `fileorganizer/metadata_extractors/psd_extractor.py`: Header pre-validation + safe_psd_open
- `requirements.txt`: psd-tools version pin

**References**:
- [GHSA-24p2-j2jr-386w](https://github.com/advisories/GHSA-24p2-j2jr-386w)
- [psd-tools issue](https://github.com/kyrofa/psd_tools/issues) (awaiting fix)

---

## Security Checklist

Before each release:
- [ ] Run full test suite (`pytest`)
- [ ] No hardcoded secrets or API keys in code
- [ ] Dependencies updated (`pip list --outdated`)
- [ ] No high/critical CVEs in dependency tree
- [ ] Archive-extraction paths validated (N-13)
- [ ] PSD parsing sandboxed / size-guarded (GHSA-24p2-j2jr-386w)
- [ ] Regex DoS patterns avoided (GHSA patterns checked)
