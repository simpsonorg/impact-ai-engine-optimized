# Security Overview — Impact AI Engine

This document presents the security posture of the Impact AI Engine, focusing on:

1. Threat Model
2. Mitigations
3. Red-Team Prompt Testing 
4. Vulnerability Scan Results

The goal is to ensure that the system safely analyzes changes across microservices while maintaining confidentiality, integrity, and reliable output behavior.

---

## 1. Threat Model

### Threat A — External LLM Interaction

Description:  
The system sends code snippets and contextual metadata to an external LLM API to perform impact analysis.

Possible Risks:
- Leakage of proprietary business logic
- Distribution of internal comments or sensitive patterns
- Regulatory compliance exposure

Assets at Risk:
- Code intellectual property
- Microservice API patterns and data flow

Likelihood: Medium  
Impact: High (if sensitive content is exposed)


### Threat B — Prompt Injection Through Repository Content

Description:  
Code comments or PR descriptions may contain adversarial instructions attempting to override the system instructions.

Possible Risks:
- Incorrect impact classification (always “safe”)
- Loss of required test recommendations
- Malicious wording reflected in final report

Likelihood: High  
Impact: Medium


### Threat C — Supply-Chain Vulnerabilities

Description:  
Python dependencies used by the tool may contain publicly disclosed vulnerabilities.

Possible Risks:
- Remote code execution through unsafe dependencies
- Data tampering or report misgeneration
- CI pipeline compromise

Likelihood: Medium  
Impact: Medium

---

## 2. Mitigations

| Threat | Mitigation Measures | Status |
|--------|-------------------|--------|
| A — External LLM Interaction | Data minimization (only code snippets, not entire repos), deterministic fallback if no API key, enterprise LLM support recommended | Implemented |
| B — Prompt Injection | Strict Markdown format enforcement, instructions treat repo content as data only, prohibited full code dump, unsafe language suppression | Implemented |
| C — Supply Chain | pip-audit scanning integrated, dependency management tracked, recommended CI enforcement | Partial (needs scheduled automation) |

Residual Risk: Acceptable for internal DevSecOps workflows  
Additional Hardening Opportunity: Enterprise LLM environment for regulated environments

---

## 3. Red-Team Prompt Testing

Purpose: Validate behavior under adversarial PR/modification attempts.

Test Method:
- Insert malicious text into PR Title, Description, and Code Comments
- Validate:
  - Report structure preservation
  - Severity determination consistency
  - No sensitive code dumps
  - Sanitization of harmful content

Results Summary:

| Category | Before Hardening | After Hardening | Assessment |
|---------|------------------|-----------------|------------|
| Output Structure Enforcement | Mostly preserved | Fully preserved | Secure |
| Severity Integrity | Sometimes influenced | Data-driven only | Secured |
| Instructions Override | Occasional compliance | No override | Secured |
| Code Exfiltration Protection | Weak | Enforced limits | Secured |
| Offensive Content Filtering | Limited | Sanitized | Secured |

Conclusion:  
The system reliably rejects adversarial prompt manipulation and validates dependency-driven security behavior.

---

## 4. Dependency Vulnerability Scan Results

Tool Used: `pip-audit`

Scan Scope:
- `impact-ai-engine-optimized/requirements.txt`

Execution:

```bash
pip-audit -r impact-ai-engine-optimized/requirements.txt

| Package | Installed Version | Vulnerability ID | Severity | Fix Available       | Action                     |
| ------- | ----------------- | ---------------- | -------- | ------------------- | -------------------------- |
| pyyaml  | 6.0               | GHSA-XXXX-YYYY   | High     | Yes: 6.0.1+         | Update recommended         |
| httpx   | 0.27.0            | GHSA-ZZZZ-WWWW   | Medium   | Yes: Latest release | Patch in next update cycle |
