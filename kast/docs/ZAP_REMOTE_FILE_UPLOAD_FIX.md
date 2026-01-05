# ZAP Remote Mode File Upload Fix

## Issue Summary

When using ZAP in remote mode with automation plans, the file upload was failing with a 502 Bad Gateway error. The root cause was discovered to be a combination of:

1. **Missing ZAP configuration flag**: `api.filexfer=true` was not enabled
2. **Incorrect API endpoint usage**: The automation plan upload required a two-step process
3. **API key not being passed correctly** in multipart file uploads

## Root Cause Analysis

### 1. ZAP Configuration Issue
ZAP requires the `api.filexfer=true` configuration flag to accept file uploads via the API. Without this flag, all file upload requests are rejected.

### 2. Incorrect API Call
The code was attempting to upload and run the automation plan in a single API call to `/JSON/automation/action/runPlan/`. However, ZAP's API requires a two-step process:
- Step 1: Upload the file using `/OTHER/core/other/fileUpload/`
- Step 2: Run the plan using `/JSON/automation/action/runPlan/`

### 3. API Key Parameter Handling
When using form data (either for file uploads or POST parameters) with the `requests` library, the session-level parameters (including the API key) were not being properly included in the request. The API key needed to be passed in both:
- HTTP header: `X-ZAP-API-Key` (required for ZAP API authentication)
- Form data: `apikey` parameter (backup authentication method)

### 4. Form Data vs Query Parameters
The `runPlan` endpoint requires parameters to be sent as form data (application/x-www-form-urlencoded), not as query parameters. Additionally, it requires the full uploaded file path, not just the filename.

## Solution Implemented

### 1. Updated ZAP Docker Commands
Added `-config api.filexfer=true` flag to all ZAP instance provisioning:

**Local mode** (`LocalZapProvider._start_zap_container()`):
```python
cmd = [
    'docker', 'run', '-d',
    '--name', self.container_name,
    '-p', f'{api_port}:8080',
    '-v', f'{self.temp_config_dir}:/zap/config',
    '-v', f'{reports_dir}:/zap/reports',
    docker_image,
    'zap.sh', '-daemon', '-port', '8080',
    '-config', f'api.key={api_key}',
    '-config', 'api.addrs.addr.name=.*',
    '-config', 'api.addrs.addr.regex=true',
    '-config', 'api.filexfer=true'  # NEW
]
```

**Cloud mode** (`CloudZapProvider.provision()`):
```python
zap_cmd = f"""docker run -d --name zap-scanner \
    -p 8080:8080 \
    -v /home/ubuntu/zap_config:/zap/config \
    -v /home/ubuntu/zap_reports:/zap/reports \
    {docker_image} \
    zap.sh -daemon -port 8080 \
    -config api.key={api_key} \
    -config api.addrs.addr.name=.* \
    -config api.addrs.addr.regex=true \
    -config api.filexfer=true"""  # NEW
```

### 2. Implemented Two-Step File Upload Process
Updated `RemoteZapProvider.upload_automation_plan()` to use the correct two-step process:

```python
def upload_automation_plan(self, plan_content, target_url):
    # Step 1: Upload the file
    files = {
        'fileContents': ('automation_plan.yaml', plan_file, 'application/octet-stream')
    }
    data = {
        'fileName': target_filename
    }
    
    upload_response = self.zap_client._make_request(
        '/OTHER/core/other/fileUpload/',
        method='POST',
        files=files,
        data=data
    )
    
    # Step 2: Extract full path and run the plan
    uploaded_path = upload_response.get('Uploaded')  # e.g., '/home/zap/.ZAP/transfer/file.yaml'
    
    run_response = self.zap_client._make_request(
        '/JSON/automation/action/runPlan/',
        method='POST',
        data={'filePath': uploaded_path}  # Form data with full path
    )
```

### 3. Enhanced API Key Handling
Updated `ZAPAPIClient._make_request()` to properly pass API keys for ALL form data requests (not just file uploads):

```python
def _make_request(self, endpoint, method='GET', params=None, data=None, files=None):
    headers = {}
    
    # For file uploads OR form data, include API key in both headers and data
    if (files or data) and self.api_key:
        headers['X-ZAP-API-Key'] = self.api_key
        if data is None:
            data = {}
        if 'apikey' not in data:
            data['apikey'] = self.api_key
    
    response = self.session.request(
        method=method,
        url=url,
        params=params,
        data=data,
        files=files,
        headers=headers,
        timeout=self.timeout
    )
```

**Key change:** Changed from `if files` to `if (files or data)` to ensure API key is included in the `X-ZAP-API-Key` header for all form data requests.

## Testing Instructions

### 1. Ensure Remote ZAP Instance Has File Transfer Enabled
When starting your remote ZAP instance, include the flag:
```bash
docker run -d \
  --name zap-scanner \
  -p 8081:8080 \
  ghcr.io/zaproxy/zaproxy:stable \
  zap.sh -daemon -port 8080 \
  -config api.key=kast01 \
  -config api.addrs.addr.name=.* \
  -config api.addrs.addr.regex=true \
  -config api.filexfer=true
```

### 2. Test Remote Mode
```bash
export KAST_ZAP_URL=http://your-zap-host:8080
kast -t example.com -v -m active \
  --set zap.execution_mode=remote \
  --set zap.remote.api_key=kast01 \
  --zap-profile=quick
```

### 3. Verify File Upload
Check the debug output for successful two-step process:
- `Step 1: Uploading file to ZAP...`
- `File upload response: {'Uploaded': '/home/zap/.ZAP/transfer/kast_automation_plan.yaml'}`
- `Step 2: Running automation plan at: /home/zap/.ZAP/transfer/kast_automation_plan.yaml`
- `Automation plan uploaded and initiated successfully`

The response should show a `planId` (e.g., `{"planId":"0"}`) indicating successful execution.

## Files Modified

1. `kast/scripts/zap_providers.py`
   - `RemoteZapProvider.upload_automation_plan()` - Implemented two-step upload
   - `LocalZapProvider._start_zap_container()` - Added api.filexfer flag
   - `CloudZapProvider.provision()` - Added api.filexfer flag

2. `kast/scripts/zap_api_client.py`
   - `ZAPAPIClient._make_request()` - Enhanced API key handling for file uploads

## Related Documentation

- ZAP API Documentation: https://www.zaproxy.org/docs/api/
- ZAP Automation Framework: https://www.zaproxy.org/docs/desktop/addons/automation-framework/
- Python Requests Multipart Upload: https://requests.readthedocs.io/en/latest/user/quickstart/#post-a-multipart-encoded-file

## Technical Details

### Why Query Parameters Failed
When using query parameters (`params={'filePath': 'file.yaml'}`), the request was rejected with:
```json
{"code":"content_type_not_supported","message":"Content type not supported."}
```

### Why Form Data Required X-ZAP-API-Key Header
When nginx acts as a reverse proxy, the API key in the session's default parameters gets lost. Testing revealed:
- Query param + form data WITHOUT header: `502 Bad Gateway` (API key not supplied)
- API key in header + form data: `200 OK` ✅
- API key in both query AND form data: `200 OK` ✅

The solution ensures the API key is sent in the `X-ZAP-API-Key` header for all form data requests.

## Credits

Issue identified and fixed based on testing with remote ZAP instance on AWS EC2 with nginx reverse proxy. The correct API usage was discovered through systematic testing with Python requests library.

## Date
2026-01-04
