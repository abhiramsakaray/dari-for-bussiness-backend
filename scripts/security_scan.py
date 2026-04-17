#!/usr/bin/env python3
"""
Scheduled Security Vulnerability Scanner
Runs daily to check for new vulnerabilities in dependencies
"""
import subprocess
import json
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_safety_check():
    """Run Safety check on Python dependencies"""
    logger.info("Running Safety check...")
    
    try:
        result = subprocess.run(
            ["safety", "check", "--json"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.stdout:
            vulnerabilities = json.loads(result.stdout)
            return vulnerabilities
        return []
    except Exception as e:
        logger.error(f"Safety check failed: {e}")
        return []


def run_pip_audit():
    """Run pip-audit on Python dependencies"""
    logger.info("Running pip-audit...")
    
    try:
        result = subprocess.run(
            ["pip-audit", "--format", "json"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.stdout:
            vulnerabilities = json.loads(result.stdout)
            return vulnerabilities
        return []
    except Exception as e:
        logger.error(f"pip-audit failed: {e}")
        return []


def analyze_vulnerabilities(safety_vulns, pip_audit_vulns):
    """Analyze and categorize vulnerabilities"""
    critical = []
    high = []
    medium = []
    low = []
    
    # Process Safety vulnerabilities
    for vuln in safety_vulns:
        severity = vuln.get("severity", "unknown").upper()
        if severity == "CRITICAL":
            critical.append(vuln)
        elif severity == "HIGH":
            high.append(vuln)
        elif severity == "MEDIUM":
            medium.append(vuln)
        else:
            low.append(vuln)
    
    # Process pip-audit vulnerabilities
    for vuln in pip_audit_vulns:
        # pip-audit uses different format
        if isinstance(vuln, dict):
            severity = vuln.get("severity", "unknown").upper()
            if severity == "CRITICAL":
                critical.append(vuln)
            elif severity == "HIGH":
                high.append(vuln)
            elif severity == "MEDIUM":
                medium.append(vuln)
            else:
                low.append(vuln)
    
    return {
        "critical": critical,
        "high": high,
        "medium": medium,
        "low": low,
        "total": len(critical) + len(high) + len(medium) + len(low)
    }


def generate_report(analysis):
    """Generate HTML report"""
    report = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .critical {{ color: #d32f2f; font-weight: bold; }}
            .high {{ color: #f57c00; font-weight: bold; }}
            .medium {{ color: #fbc02d; }}
            .low {{ color: #388e3c; }}
            table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; }}
        </style>
    </head>
    <body>
        <h1>Security Vulnerability Scan Report</h1>
        <p><strong>Date:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h2>Summary</h2>
        <ul>
            <li class="critical">Critical: {len(analysis['critical'])}</li>
            <li class="high">High: {len(analysis['high'])}</li>
            <li class="medium">Medium: {len(analysis['medium'])}</li>
            <li class="low">Low: {len(analysis['low'])}</li>
        </ul>
        
        <h2>Total Vulnerabilities: {analysis['total']}</h2>
    """
    
    if analysis['critical']:
        report += "<h3 class='critical'>Critical Vulnerabilities</h3><table>"
        report += "<tr><th>Package</th><th>Vulnerability</th><th>Affected Version</th></tr>"
        for vuln in analysis['critical']:
            report += f"<tr><td>{vuln.get('package', 'N/A')}</td>"
            report += f"<td>{vuln.get('vulnerability', 'N/A')}</td>"
            report += f"<td>{vuln.get('affected_version', 'N/A')}</td></tr>"
        report += "</table>"
    
    if analysis['high']:
        report += "<h3 class='high'>High Severity Vulnerabilities</h3><table>"
        report += "<tr><th>Package</th><th>Vulnerability</th><th>Affected Version</th></tr>"
        for vuln in analysis['high']:
            report += f"<tr><td>{vuln.get('package', 'N/A')}</td>"
            report += f"<td>{vuln.get('vulnerability', 'N/A')}</td>"
            report += f"<td>{vuln.get('affected_version', 'N/A')}</td></tr>"
        report += "</table>"
    
    report += "</body></html>"
    return report


def send_alert_email(report, recipients):
    """Send email alert if vulnerabilities found"""
    # TODO: Configure SMTP settings
    logger.info(f"Would send email alert to {recipients}")
    # In production, implement actual email sending
    pass


def main():
    """Main execution"""
    logger.info("Starting security vulnerability scan...")
    
    # Run scans
    safety_vulns = run_safety_check()
    pip_audit_vulns = run_pip_audit()
    
    # Analyze results
    analysis = analyze_vulnerabilities(safety_vulns, pip_audit_vulns)
    
    # Generate report
    report = generate_report(analysis)
    
    # Save report
    report_dir = Path("reports/security")
    report_dir.mkdir(parents=True, exist_ok=True)
    
    report_file = report_dir / f"scan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    report_file.write_text(report)
    
    logger.info(f"Report saved to {report_file}")
    
    # Alert if critical/high vulnerabilities found
    if analysis['critical'] or analysis['high']:
        logger.warning(
            f"⚠️  Found {len(analysis['critical'])} critical and "
            f"{len(analysis['high'])} high severity vulnerabilities!"
        )
        # send_alert_email(report, ["security@example.com"])
        return 1
    
    logger.info("✅ No critical or high severity vulnerabilities found")
    return 0


if __name__ == "__main__":
    exit(main())
