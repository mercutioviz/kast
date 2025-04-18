#!/usr/bin/env python3

import os
import json
import time
from datetime import datetime
from jinja2 import Environment, FileSystemLoader
from src.modules.utils.logger import get_module_logger

# Module-specific logger
logger = get_module_logger(__name__)

def generate_report(target, results, output_dir):
    """
    Generate a comprehensive HTML report from scan results
    
    Args:
        target (str): The target that was scanned
        results (dict): The scan results (contains 'recon' and/or 'vuln' keys)
        output_dir (str): Directory to save the report
        
    Returns:
        str: Path to the generated report
    """
    logger.info(f"Generating report for {target}")
    
    # Create report directory if it doesn't exist
    report_dir = os.path.join(output_dir, 'report')
    os.makedirs(report_dir, exist_ok=True)
    
    # Define report file path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_file = os.path.join(report_dir, f'kast_report_{timestamp}.html')
    
    # Determine which scans were performed
    recon_performed = 'recon' in results
    vuln_performed = 'vuln' in results
    
    # Prepare report data
    report_data = {
        'target': target,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'recon_performed': recon_performed,
        'vuln_performed': vuln_performed,
        'recon_results': process_recon_results(results.get('recon', {})) if recon_performed else None,
        'vuln_results': process_vuln_results(results.get('vuln', {})) if vuln_performed else None
    }
    
    # Generate HTML report using template
    try:
        # Get the template directory
        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')
        
        # If template directory doesn't exist, create it and generate a default template
        if not os.path.exists(template_dir):
            os.makedirs(template_dir, exist_ok=True)
            create_default_template(template_dir)
        
        # Set up Jinja2 environment
        env = Environment(loader=FileSystemLoader(template_dir))
        template = env.get_template('report_template.html')
        
        # Render the template with our data
        html_content = template.render(**report_data)
        
        # Write the report to file
        with open(report_file, 'w') as f:
            f.write(html_content)
        
        logger.info(f"Report generated successfully: {report_file}")
        return report_file
        
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        
        # Fallback to a simple report if template rendering fails
        generate_simple_report(target, results, report_file)
        return report_file

def process_recon_results(recon_results):
    """
    Process reconnaissance results for the report
    
    Args:
        recon_results (dict): The reconnaissance results
        
    Returns:
        dict: Processed reconnaissance results
    """
    processed = {
        'summary': {
            'tools_run': 0,
            'tools_succeeded': 0,
            'tools_failed': 0
        },
        'tools': {}
    }
    
    # Process WhatWeb results
    if 'whatweb' in recon_results:
        processed['tools']['whatweb'] = process_whatweb_results(recon_results['whatweb'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['whatweb'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    # Process theHarvester results
    if 'theharvester' in recon_results:
        processed['tools']['theharvester'] = process_theharvester_results(recon_results['theharvester'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['theharvester'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    # Process DNSenum results
    if 'dnsenum' in recon_results:
        processed['tools']['dnsenum'] = process_dnsenum_results(recon_results['dnsenum'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['dnsenum'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    # Process SSLScan results
    if 'sslscan' in recon_results:
        processed['tools']['sslscan'] = process_sslscan_results(recon_results['sslscan'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['sslscan'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    # Process wafw00f results
    if 'wafw00f' in recon_results:
        processed['tools']['wafw00f'] = process_wafw00f_results(recon_results['wafw00f'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['wafw00f'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    # Process SSL Labs results
    if 'ssllabs' in recon_results:
        processed['tools']['ssllabs'] = process_ssllabs_results(recon_results['ssllabs'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['ssllabs'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    # Process SecurityHeaders results
    if 'securityheaders' in recon_results:
        processed['tools']['securityheaders'] = process_securityheaders_results(recon_results['securityheaders'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['securityheaders'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    # Process Mozilla Observatory results
    if 'mozilla_observatory' in recon_results:
        processed['tools']['mozilla_observatory'] = process_observatory_results(recon_results['mozilla_observatory'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['mozilla_observatory'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    # Process browser recon results
    if 'browser' in recon_results:
        processed['tools']['browser'] = process_browser_results(recon_results['browser'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['browser'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
        else:
            processed['summary']['tools_failed'] += 1
    
    return processed

def process_vuln_results(vuln_results):
    """
    Process vulnerability scanning results for the report
    
    Args:
        vuln_results (dict): The vulnerability scanning results
        
    Returns:
        dict: Processed vulnerability scanning results
    """
    processed = {
        'summary': {
            'tools_run': 0,
            'tools_succeeded': 0,
            'tools_failed': 0,
            'vulnerabilities': {
                'high': 0,
                'medium': 0,
                'low': 0,
                'info': 0
            }
        },
        'tools': {}
    }
    
    # Process Nikto results
    if 'nikto' in vuln_results:
        processed['tools']['nikto'] = process_nikto_results(vuln_results['nikto'])
        processed['summary']['tools_run'] += 1
        if processed['tools']['nikto'].get('success', False):
            processed['summary']['tools_succeeded'] += 1
            
            # Add vulnerability counts
            if 'summary' in processed['tools']['nikto'] and 'vulnerabilities' in processed['tools']['nikto']['summary']:
                vulns = processed['tools']['nikto']['summary']['vulnerabilities']
                processed['summary']['vulnerabilities']['high'] += vulns.get('high', 0)
                processed['summary']['vulnerabilities']['medium'] += vulns.get('medium', 0)
                processed['summary']['vulnerabilities']['low'] += vulns.get('low', 0)
                processed['summary']['vulnerabilities']['info'] += vulns.get('info', 0)
        else:
            processed['summary']['tools_failed'] += 1
    
    # Add other vulnerability scanners here as they are implemented
    
    # Calculate total vulnerabilities
    processed['summary']['total_vulnerabilities'] = (
        processed['summary']['vulnerabilities']['high'] +
        processed['summary']['vulnerabilities']['medium'] +
        processed['summary']['vulnerabilities']['low'] +
        processed['summary']['vulnerabilities']['info']
    )
    
    return processed

def process_whatweb_results(results):
    """Process WhatWeb results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'command': results.get('command', 'Unknown command')
        }
    
    # Process actual results
    try:
        technologies = []
        
        # WhatWeb output format can vary, try to handle different formats
        if isinstance(results, list):
            for entry in results:
                if isinstance(entry, dict) and 'plugins' in entry:
                    for plugin, data in entry.get('plugins', {}).items():
                        technologies.append({
                            'name': plugin,
                            'version': data.get('version', ['Unknown'])[0] if isinstance(data.get('version', []), list) else data.get('version', 'Unknown'),
                            'details': data
                        })
        elif isinstance(results, dict) and 'target' in results:
            for plugin, data in results.get('plugins', {}).items():
                technologies.append({
                    'name': plugin,
                    'version': data.get('version', ['Unknown'])[0] if isinstance(data.get('version', []), list) else data.get('version', 'Unknown'),
                    'details': data
                })
        
        return {
            'success': True,
            'technologies': technologies,
            'count': len(technologies)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing WhatWeb results: {str(e)}"
        }

def process_theharvester_results(results):
    """Process theHarvester results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'command': results.get('command', 'Unknown command')
        }
    
    # Process actual results
    try:
        emails = results.get('emails', [])
        hosts = results.get('hosts', [])
        vhosts = results.get('vhosts', [])
        
        return {
            'success': True,
            'emails': emails,
            'hosts': hosts,
            'vhosts': vhosts,
            'email_count': len(emails),
            'host_count': len(hosts),
            'vhost_count': len(vhosts)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing theHarvester results: {str(e)}"
        }

def process_dnsenum_results(results):
    """Process DNSenum results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'command': results.get('command', 'Unknown command')
        }
    
    # Process actual results
    try:
        nameservers = results.get('nameservers', [])
        mx_records = results.get('mx_records', [])
        subdomains = results.get('subdomains', [])
        hosts = results.get('hosts', [])
        
        return {
            'success': True,
            'nameservers': nameservers,
            'mx_records': mx_records,
            'subdomains': subdomains,
            'hosts': hosts,
            'nameserver_count': len(nameservers),
            'mx_record_count': len(mx_records),
            'subdomain_count': len(subdomains),
            'host_count': len(hosts)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing DNSenum results: {str(e)}"
        }

def process_sslscan_results(results):
    """Process SSLScan results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'command': results.get('command', 'Unknown command')
        }
    
    # Process actual results
    try:
        protocols = {}
        ciphers = []
        certificate = {}
        
        # Extract protocols
        if 'protocols' in results:
            protocols = results['protocols']
        
        # Extract ciphers
        if 'ciphers' in results:
            ciphers = results['ciphers']
        
        # Extract certificate info
        if 'certificate' in results:
            certificate = results['certificate']
        
        return {
            'success': True,
            'protocols': protocols,
            'ciphers': ciphers,
            'certificate': certificate,
            'cipher_count': len(ciphers)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing SSLScan results: {str(e)}"
        }

def process_wafw00f_results(results):
    """Process wafw00f results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'command': results.get('command', 'Unknown command')
        }
    
    # Process actual results
    try:
        detected_wafs = []
        
        if 'detected_wafs' in results:
            detected_wafs = results['detected_wafs']
        
        return {
            'success': True,
            'detected_wafs': detected_wafs,
            'waf_detected': len(detected_wafs) > 0,
            'waf_count': len(detected_wafs)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing wafw00f results: {str(e)}"
        }

def process_ssllabs_results(results):
    """Process SSL Labs results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'api': results.get('api', 'SSL Labs')
        }
    
    # Process actual results
    try:
        grade = None
        endpoints = []
        
        if 'endpoints' in results:
            for endpoint in results['endpoints']:
                endpoints.append({
                    'ip': endpoint.get('ipAddress', 'Unknown'),
                    'grade': endpoint.get('grade', 'Unknown'),
                    'has_warnings': endpoint.get('hasWarnings', False),
                    'is_exceptional': endpoint.get('isExceptional', False)
                })
                
                # Use the first endpoint's grade as the overall grade
                if grade is None and 'grade' in endpoint:
                    grade = endpoint['grade']
        
        return {
            'success': True,
            'grade': grade,
            'endpoints': endpoints,
            'endpoint_count': len(endpoints)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing SSL Labs results: {str(e)}"
        }

def process_securityheaders_results(results):
    """Process SecurityHeaders.io results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'api': results.get('api', 'SecurityHeaders.io')
        }
    
    # Process actual results
    try:
        headers = {}
        
        if 'security_headers' in results:
            headers = results['security_headers']
        
        return {
            'success': True,
            'headers': headers,
            'header_count': len(headers) if headers else 0
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing SecurityHeaders.io results: {str(e)}"
        }

def process_observatory_results(results):
    """Process Mozilla Observatory results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'api': results.get('api', 'Mozilla Observatory')
        }
    
    # Process actual results
    try:
        grade = None
        score = None
        tests = []
        
        if 'summary' in results:
            summary = results['summary']
            grade = summary.get('grade')
            score = summary.get('score')
            tests = summary.get('tests', [])
        
        return {
            'success': True,
            'grade': grade,
            'score': score,
            'tests': tests,
            'test_count': len(tests)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing Mozilla Observatory results: {str(e)}"
        }

def process_browser_results(results):
    """Process browser-based reconnaissance results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'tool': results.get('tool', 'Browser Reconnaissance')
        }
    
    # Process actual results
    try:
        js_files = results.get('js_files', [])
        forms = results.get('forms', [])
        links = results.get('links', [])
        cookies = results.get('cookies', [])
        frameworks = results.get('frameworks', [])
        
        return {
            'success': True,
            'js_files': js_files,
            'forms': forms,
            'links': links,
            'cookies': cookies,
            'frameworks': frameworks,
            'js_file_count': len(js_files),
            'form_count': len(forms),
            'link_count': len(links),
            'cookie_count': len(cookies),
            'framework_count': len(frameworks)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing browser reconnaissance results: {str(e)}"
        }

def process_nikto_results(results):
    """Process Nikto results"""
    if results is None or isinstance(results, str) or 'error' in results:
        return {
            'success': False,
            'error': results if isinstance(results, str) else results.get('error', 'Unknown error')
        }
    
    # Check if it's a dry run
    if isinstance(results, dict) and results.get('dry_run', False):
        return {
            'success': True,
            'dry_run': True,
            'command': results.get('command', 'Unknown command'),
            'scan_type': results.get('scan_type', 'Unknown')
        }
    
    # Process actual results
    try:
        summary = results.get('summary', {})
        findings = summary.get('findings', [])
        
        return {
            'success': True,
            'summary': summary,
            'findings': findings,
            'finding_count': len(findings),
            'scan_type': results.get('scan_type', 'Unknown'),
            'duration': results.get('duration', 0)
        }
    except Exception as e:
        return {
            'success': False,
            'error': f"Error processing Nikto results: {str(e)}"
        }

def create_default_template(template_dir):
    """
    Create a default HTML report template
    
    Args:
        template_dir (str): Directory to save the template
    """
    template_path = os.path.join(template_dir, 'report_template.html')
    
    template_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>KAST Security Scan Report - {{ target }}</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }
        h1, h2, h3, h4 {
            color: #2c3e50;
        }
        .header {
            background-color: #3498db;
            color: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 5px;
        }
        .section {
            margin-bottom: 30px;
            padding: 20px;
            background-color: #f9f9f9;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .summary-box {
            display: inline-block;
            width: 200px;
            padding: 15px;
            margin: 10px;
            text-align: center;
            border-radius: 5px;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .success {
            background-color: #2ecc71;
            color: white;
        }
        .warning {
            background-color: #f39c12;
            color: white;
        }
        .danger {
            background-color: #e74c3c;
            color: white;
        }
        .info {
            background-color: #3498db;
            color: white;
        }
        .neutral {
            background-color: #95a5a6;
            color: white;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .footer {
            margin-top: 50px;
            text-align: center;
            font-size: 0.8em;
            color: #7f8c8d;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>KAST Security Scan Report</h1>
        <p>Target: {{ target }}</p>
        <p>Generated: {{ timestamp }}</p>
    </div>

    <div class="section">
        <h2>Executive Summary</h2>
        <p>This report presents the findings from a security scan of {{ target }} performed using KAST (Kali Automated Scanning Tool).</p>
        
        {% if recon_performed and vuln_performed %}
            <p>Both reconnaissance and vulnerability scanning were performed.</p>
        {% elif recon_performed %}
            <p>Only reconnaissance scanning was performed. No vulnerability scanning was conducted.</p>
        {% elif vuln_performed %}
            <p>Only vulnerability scanning was performed. No reconnaissance was conducted.</p>
        {% endif %}
        
        {% if vuln_performed and vuln_results.summary.total_vulnerabilities > 0 %}
            <div class="summary-box {% if vuln_results.summary.vulnerabilities.high > 0 %}danger{% elif vuln_results.summary.vulnerabilities.medium > 0 %}warning{% else %}info{% endif %}">
                <h3>{{ vuln_results.summary.total_vulnerabilities }}</h3>
                <p>Total Vulnerabilities</p>
            </div>
            <div class="summary-box danger">
                <h3>{{ vuln_results.summary.vulnerabilities.high }}</h3>
                <p>High Severity</p>
            </div>
            <div class="summary-box warning">
                <h3>{{ vuln_results.summary.vulnerabilities.medium }}</h3>
                <p>Medium Severity</p>
            </div>
            <div class="summary-box info">
                <h3>{{ vuln_results.summary.vulnerabilities.low }}</h3>
                <p>Low Severity</p>
            </div>
            <div class="summary-box neutral">
                <h3>{{ vuln_results.summary.vulnerabilities.info }}</h3>
                <p>Informational</p>
            </div>
        {% endif %}
    </div>

    {% if recon_performed %}
    <div class="section">
        <h2>Reconnaissance Results</h2>
        <p>{{ recon_results.summary.tools_succeeded }} out of {{ recon_results.summary.tools_run }} reconnaissance tools completed successfully.</p>
        
        {% if 'whatweb' in recon_results.tools %}
            <h3>Web Technologies (WhatWeb)</h3>
            {% if recon_results.tools.whatweb.success %}
                {% if recon_results.tools.whatweb.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.whatweb.command }}</p>
                {% else %}
                    <p>Detected {{ recon_results.tools.whatweb.count }} technologies:</p>
                    <table>
                        <tr>
                            <th>Technology</th>
                            <th>Version</th>
                        </tr>
                        {% for tech in recon_results.tools.whatweb.technologies %}
                        <tr>
                            <td>{{ tech.name }}</td>
                            <td>{{ tech.version }}</td>
                        </tr>
                        {% endfor %}
                    </table>
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.whatweb.error }}</p>
            {% endif %}
        {% endif %}
        
        {% if 'theharvester' in recon_results.tools %}
            <h3>Email and Domain Information (theHarvester)</h3>
            {% if recon_results.tools.theharvester.success %}
                {% if recon_results.tools.theharvester.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.theharvester.command }}</p>
                {% else %}
                    <p>Found {{ recon_results.tools.theharvester.email_count }} emails, {{ recon_results.tools.theharvester.host_count }} hosts, and {{ recon_results.tools.theharvester.vhost_count }} virtual hosts.</p>
                    
                    {% if recon_results.tools.theharvester.email_count > 0 %}
                        <h4>Emails</h4>
                        <ul>
                            {% for email in recon_results.tools.theharvester.emails %}
                                <li>{{ email }}</li>
                            {% endfor %}
                        </ul>
                    {% endif %}
                    
                    {% if recon_results.tools.theharvester.host_count > 0 %}
                        <h4>Hosts</h4>
                        <ul>
                            {% for host in recon_results.tools.theharvester.hosts %}
                                <li>{{ host }}</li>
                            {% endfor %}
                        </ul>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.theharvester.error }}</p>
            {% endif %}
        {% endif %}
        
        {% if 'dnsenum' in recon_results.tools %}
            <h3>DNS Information (DNSenum)</h3>
            {% if recon_results.tools.dnsenum.success %}
                {% if recon_results.tools.dnsenum.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.dnsenum.command }}</p>
                {% else %}
                    <p>Found {{ recon_results.tools.dnsenum.nameserver_count }} nameservers, {{ recon_results.tools.dnsenum.mx_record_count }} MX records, and {{ recon_results.tools.dnsenum.subdomain_count }} subdomains.</p>
                    
                    {% if recon_results.tools.dnsenum.nameserver_count > 0 %}
                        <h4>Nameservers</h4>
                        <ul>
                            {% for ns in recon_results.tools.dnsenum.nameservers %}
                                <li>{{ ns }}</li>
                            {% endfor %}
                        </ul>
                    {% endif %}
                    
                    {% if recon_results.tools.dnsenum.subdomain_count > 0 %}
                        <h4>Subdomains</h4>
                        <ul>
                            {% for subdomain in recon_results.tools.dnsenum.subdomains %}
                                <li>{{ subdomain.hostname }} ({{ subdomain.ip }})</li>
                            {% endfor %}
                        </ul>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.dnsenum.error }}</p>
            {% endif %}
        {% endif %}
        
        {% if 'sslscan' in recon_results.tools %}
            <h3>SSL/TLS Configuration (SSLScan)</h3>
            {% if recon_results.tools.sslscan.success %}
                {% if recon_results.tools.sslscan.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.sslscan.command }}</p>
                {% else %}
                    <p>Found {{ recon_results.tools.sslscan.cipher_count }} ciphers.</p>
                    
                    {% if recon_results.tools.sslscan.certificate %}
                        <h4>Certificate Information</h4>
                        <table>
                            {% for key, value in recon_results.tools.sslscan.certificate.items() %}
                            <tr>
                                <td>{{ key }}</td>
                                <td>{{ value }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.sslscan.error }}</p>
            {% endif %}
        {% endif %}
        
        {% if 'wafw00f' in recon_results.tools %}
            <h3>Web Application Firewall Detection (wafw00f)</h3>
            {% if recon_results.tools.wafw00f.success %}
                {% if recon_results.tools.wafw00f.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.wafw00f.command }}</p>
                {% else %}
                    {% if recon_results.tools.wafw00f.waf_detected %}
                        <p>Detected {{ recon_results.tools.wafw00f.waf_count }} Web Application Firewalls:</p>
                        <ul>
                            {% for waf in recon_results.tools.wafw00f.detected_wafs %}
                                <li>{{ waf }}</li>
                            {% endfor %}
                        </ul>
                    {% else %}
                        <p>No Web Application Firewalls detected.</p>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.wafw00f.error }}</p>
            {% endif %}
        {% endif %}
        
        {% if 'ssllabs' in recon_results.tools %}
            <h3>SSL/TLS Analysis (SSL Labs)</h3>
            {% if recon_results.tools.ssllabs.success %}
                {% if recon_results.tools.ssllabs.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.ssllabs.api }}</p>
                {% else %}
                    <p>Overall Grade: {{ recon_results.tools.ssllabs.grade }}</p>
                    
                    {% if recon_results.tools.ssllabs.endpoint_count > 0 %}
                        <h4>Endpoints</h4>
                        <table>
                            <tr>
                                <th>IP Address</th>
                                <th>Grade</th>
                                <th>Warnings</th>
                            </tr>
                            {% for endpoint in recon_results.tools.ssllabs.endpoints %}
                            <tr>
                                <td>{{ endpoint.ip }}</td>
                                <td>{{ endpoint.grade }}</td>
                                <td>{{ "Yes" if endpoint.has_warnings else "No" }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.ssllabs.error }}</p>
            {% endif %}
        {% endif %}
        
        {% if 'securityheaders' in recon_results.tools %}
            <h3>HTTP Security Headers (SecurityHeaders.io)</h3>
            {% if recon_results.tools.securityheaders.success %}
                {% if recon_results.tools.securityheaders.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.securityheaders.api }}</p>
                {% else %}
                    <p>Found {{ recon_results.tools.securityheaders.header_count }} security headers.</p>
                    
                    {% if recon_results.tools.securityheaders.headers %}
                        <table>
                            <tr>
                                <th>Header</th>
                                <th>Value</th>
                            </tr>
                            {% for header, value in recon_results.tools.securityheaders.headers.items() %}
                            <tr>
                                <td>{{ header }}</td>
                                <td>{{ value }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.securityheaders.error }}</p>
            {% endif %}
        {% endif %}
        
        {% if 'mozilla_observatory' in recon_results.tools %}
            <h3>Web Security (Mozilla Observatory)</h3>
            {% if recon_results.tools.mozilla_observatory.success %}
                {% if recon_results.tools.mozilla_observatory.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.mozilla_observatory.api }}</p>
                {% else %}
                    <p>Grade: {{ recon_results.tools.mozilla_observatory.grade }}</p>
                    <p>Score: {{ recon_results.tools.mozilla_observatory.score }}</p>
                    
                    {% if recon_results.tools.mozilla_observatory.test_count > 0 %}
                        <h4>Tests</h4>
                        <table>
                            <tr>
                                <th>Test</th>
                                <th>Result</th>
                                <th>Pass</th>
                            </tr>
                            {% for test in recon_results.tools.mozilla_observatory.tests %}
                            <tr>
                                <td>{{ test.name }}</td>
                                <td>{{ test.result }}</td>
                                <td>{{ "Yes" if test.pass else "No" }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.mozilla_observatory.error }}</p>
            {% endif %}
        {% endif %}
        
        {% if 'browser' in recon_results.tools %}
            <h3>Browser-Based Reconnaissance</h3>
            {% if recon_results.tools.browser.success %}
                {% if recon_results.tools.browser.dry_run %}
                    <p>Dry run mode: {{ recon_results.tools.browser.tool }}</p>
                {% else %}
                    <p>Found {{ recon_results.tools.browser.js_file_count }} JavaScript files, {{ recon_results.tools.browser.form_count }} forms, and {{ recon_results.tools.browser.cookie_count }} cookies.</p>
                    
                    {% if recon_results.tools.browser.framework_count > 0 %}
                        <h4>Detected Frameworks</h4>
                        <ul>
                            {% for framework in recon_results.tools.browser.frameworks %}
                                <li>{{ framework }}</li>
                            {% endfor %}
                        </ul>
                    {% endif %}
                    
                    {% if recon_results.tools.browser.form_count > 0 %}
                        <h4>Forms</h4>
                        <table>
                            <tr>
                                <th>Action</th>
                                <th>Method</th>
                                <th>Inputs</th>
                            </tr>
                            {% for form in recon_results.tools.browser.forms %}
                            <tr>
                                <td>{{ form.action }}</td>
                                <td>{{ form.method }}</td>
                                <td>{{ form.inputs|length }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ recon_results.tools.browser.error }}</p>
            {% endif %}
        {% endif %}
    </div>
    {% endif %}

    {% if vuln_performed %}
    <div class="section">
        <h2>Vulnerability Scan Results</h2>
        <p>{{ vuln_results.summary.tools_succeeded }} out of {{ vuln_results.summary.tools_run }} vulnerability scanning tools completed successfully.</p>
        
        {% if 'nikto' in vuln_results.tools %}
            <h3>Web Vulnerability Scan (Nikto)</h3>
            {% if vuln_results.tools.nikto.success %}
                {% if vuln_results.tools.nikto.dry_run %}
                    <p>Dry run mode: {{ vuln_results.tools.nikto.command }}</p>
                {% else %}
                    <p>Scan type: {{ vuln_results.tools.nikto.scan_type }}</p>
                    <p>Duration: {{ vuln_results.tools.nikto.duration }} seconds</p>
                    <p>Found {{ vuln_results.tools.nikto.finding_count }} vulnerabilities.</p>
                    
                    {% if vuln_results.tools.nikto.finding_count > 0 %}
                        <h4>Findings</h4>
                        <table>
                            <tr>
                                <th>Severity</th>
                                <th>Description</th>
                                <th>URL</th>
                                <th>OSVDB</th>
                            </tr>
                            {% for finding in vuln_results.tools.nikto.findings %}
                            <tr>
                                <td>{{ finding.severity }}</td>
                                <td>{{ finding.message }}</td>
                                <td>{{ finding.url }}</td>
                                <td>{{ finding.osvdb }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    {% endif %}
                {% endif %}
            {% else %}
                <p>Error: {{ vuln_results.tools.nikto.error }}</p>
            {% endif %}
        {% endif %}
        
        <!-- Add more vulnerability scanners here as they are implemented -->
    </div>
    {% endif %}

    <div class="footer">
        <p>Generated by KAST (Kali Automated Scanning Tool) on {{ timestamp }}</p>
        <p>This report is for informational purposes only. Always verify findings before taking action.</p>
    </div>
</body>
</html>
"""
    
    with open(template_path, 'w') as f:
        f.write(template_content)
    
    logger.info(f"Default report template created at {template_path}")

def generate_simple_report(target, results, report_file):
    """
    Generate a simple HTML report as a fallback
    
    Args:
        target (str): The target that was scanned
        results (dict): The scan results
        report_file (str): Path to save the report
    """
    logger.info("Generating simple fallback report")
    
    # Determine which scans were performed
    recon_performed = 'recon' in results
    vuln_performed = 'vuln' in results
    
    # Create a simple HTML report
    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>KAST Scan Report - {target}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        h1 {{ color: #2c3e50; }}
        h2 {{ color: #3498db; }}
        .section {{ margin-bottom: 20px; padding: 10px; border: 1px solid #ddd; }}
    </style>
</head>
<body>
    <h1>KAST Security Scan Report</h1>
    <p><strong>Target:</strong> {target}</p>
    <p><strong>Generated:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    
    <div class="section">
        <h2>Scan Summary</h2>
        <p>This report presents the findings from a security scan of {target} performed using KAST (Kali Automated Scanning Tool).</p>
        
        <p>
        {'Both reconnaissance and vulnerability scanning were performed.' if recon_performed and vuln_performed else
         'Only reconnaissance scanning was performed. No vulnerability scanning was conducted.' if recon_performed else
         'Only vulnerability scanning was performed. No reconnaissance was conducted.' if vuln_performed else
         'No scans were performed.'}
        </p>
    </div>
    
    {'<div class="section"><h2>Reconnaissance Results</h2><p>See detailed results in the recon directory.</p></div>' if recon_performed else ''}
    
    {'<div class="section"><h2>Vulnerability Scan Results</h2><p>See detailed results in the vuln directory.</p></div>' if vuln_performed else ''}
    
    <p><em>Note: This is a simplified report generated as a fallback due to template rendering issues.</em></p>
</body>
</html>
"""
    
    # Write the report to file
    with open(report_file, 'w') as f:
        f.write(html)
    
    logger.info(f"Simple fallback report generated: {report_file}")

# If you need to test the report generator directly
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate a report from scan results")
    parser.add_argument("target", help="Target that was scanned")
    parser.add_argument("results_dir", help="Directory containing scan results")
    parser.add_argument("output_dir", help="Directory to save the report")
    
    args = parser.parse_args()
    
    # Load results from files
    results = {}
    
    recon_file = os.path.join(args.results_dir, 'recon_results.json')
    if os.path.exists(recon_file):
        with open(recon_file, 'r') as f:
            results['recon'] = json.load(f)
    
    vuln_file = os.path.join(args.results_dir, 'vuln_results.json')
    if os.path.exists(vuln_file):
        with open(vuln_file, 'r') as f:
            results['vuln'] = json.load(f)
    
    # Generate the report
    report_path = generate_report(args.target, results, args.output_dir)
    print(f"Report generated: {report_path}")
