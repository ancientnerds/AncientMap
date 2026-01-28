# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability, please
report it responsibly.

### How to Report

**DO NOT** open a public GitHub issue for security vulnerabilities.

Instead, please send a detailed report to:

**Use GitHub's [Private Vulnerability Reporting](../../security/advisories/new) feature.**

This allows you to report security issues privately without exposing them publicly.

### What to Include

Please include the following in your report:

1. **Description** of the vulnerability
2. **Steps to reproduce** the issue
3. **Potential impact** of the vulnerability
4. **Suggested fix** (if you have one)
5. **Your contact information** for follow-up questions

### What to Expect

- **Acknowledgment**: We will acknowledge receipt within 48 hours
- **Assessment**: We will assess the vulnerability within 7 days
- **Updates**: We will keep you informed of our progress
- **Resolution**: We aim to resolve critical issues within 30 days
- **Credit**: With your permission, we will credit you in our release notes

### Scope

The following are in scope for security reports:

- Authentication and authorization bypasses
- SQL injection, XSS, CSRF vulnerabilities
- Sensitive data exposure
- Remote code execution
- Server-side request forgery (SSRF)
- Insecure direct object references

### Out of Scope

- Denial of service attacks
- Social engineering attacks
- Physical attacks
- Issues in dependencies (report these to the dependency maintainers)
- Issues requiring unlikely user interaction

## Security Best Practices for Contributors

### Credentials

- **NEVER** commit API keys, passwords, or secrets to the repository
- Use environment variables for all sensitive configuration
- Use `.env` files locally (they are gitignored)
- Rotate any credentials that may have been exposed

### Code

- Use parameterized queries for all database operations
- Validate and sanitize all user input
- Use secure session management
- Implement proper CORS policies
- Keep dependencies updated

### Data

- Do not store sensitive user data unnecessarily
- Implement proper access controls
- Log security-relevant events
- Follow data protection regulations (GDPR, etc.)

## Security Features

This project implements several security measures:

- **Rate limiting**: API endpoints are rate-limited to prevent abuse
- **Input validation**: All inputs are validated using Pydantic models
- **CORS**: Cross-origin requests are restricted to allowed origins
- **Session management**: Sessions expire after configurable timeout
- **Bot protection**: Cloudflare Turnstile integration for sensitive endpoints
- **SQL injection prevention**: Parameterized queries via SQLAlchemy

## Dependency Security

We regularly audit our dependencies for known vulnerabilities:

```bash
# Python
pip-audit

# JavaScript
npm audit
```

If you notice outdated dependencies with known vulnerabilities, please open an
issue or submit a PR to update them.

## Acknowledgments

We thank the following individuals for responsibly disclosing security issues:

*No reports yet - be the first!*
