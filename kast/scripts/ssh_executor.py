"""
SSH Executor for ZAP Cloud Plugin
Handles SSH connections and remote command execution on cloud instances
"""

import paramiko
import time
import os
from pathlib import Path


class SSHExecutor:
    """Handles SSH operations for remote ZAP instance management"""
    
    def __init__(self, host, user, private_key_path, timeout=300, retry_attempts=5, debug_callback=None):
        """
        Initialize SSH executor
        
        :param host: Remote host IP address
        :param user: SSH username
        :param private_key_path: Path to private SSH key
        :param timeout: Connection timeout in seconds
        :param retry_attempts: Number of connection retry attempts
        :param debug_callback: Optional callback function for debug messages
        """
        self.host = host
        self.user = user
        self.private_key_path = Path(private_key_path).expanduser()
        self.timeout = timeout
        self.retry_attempts = retry_attempts
        self.debug = debug_callback or (lambda x: None)
        self.client = None
        self.sftp = None
    
    def connect(self):
        """
        Establish SSH connection with retry logic
        
        :return: True if connected, False otherwise
        """
        for attempt in range(1, self.retry_attempts + 1):
            try:
                self.debug(f"SSH connection attempt {attempt}/{self.retry_attempts} to {self.user}@{self.host}")
                
                # Create SSH client
                self.client = paramiko.SSHClient()
                self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                # Load private key
                private_key = paramiko.RSAKey.from_private_key_file(str(self.private_key_path))
                
                # Connect
                self.client.connect(
                    hostname=self.host,
                    username=self.user,
                    pkey=private_key,
                    timeout=self.timeout,
                    banner_timeout=30,
                    auth_timeout=30
                )
                
                self.debug(f"SSH connection established to {self.host}")
                
                # Open SFTP client
                self.sftp = self.client.open_sftp()
                
                return True
                
            except paramiko.ssh_exception.NoValidConnectionsError as e:
                self.debug(f"Connection failed (attempt {attempt}): {e}")
                if attempt < self.retry_attempts:
                    time.sleep(10 * attempt)  # Exponential backoff
                    
            except paramiko.ssh_exception.SSHException as e:
                self.debug(f"SSH error (attempt {attempt}): {e}")
                if attempt < self.retry_attempts:
                    time.sleep(10 * attempt)
                    
            except Exception as e:
                self.debug(f"Unexpected error (attempt {attempt}): {e}")
                if attempt < self.retry_attempts:
                    time.sleep(10 * attempt)
        
        return False
    
    def execute_command(self, command, timeout=300):
        """
        Execute a command on the remote host
        
        :param command: Command to execute
        :param timeout: Command timeout in seconds
        :return: Tuple of (exit_code, stdout, stderr)
        """
        if not self.client:
            raise RuntimeError("SSH client not connected")
        
        try:
            self.debug(f"Executing command: {command}")
            
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            
            exit_code = stdout.channel.recv_exit_status()
            stdout_data = stdout.read().decode('utf-8')
            stderr_data = stderr.read().decode('utf-8')
            
            self.debug(f"Command exit code: {exit_code}")
            if stdout_data:
                self.debug(f"STDOUT: {stdout_data[:500]}")  # Log first 500 chars
            if stderr_data:
                self.debug(f"STDERR: {stderr_data[:500]}")
            
            return exit_code, stdout_data, stderr_data
            
        except Exception as e:
            self.debug(f"Command execution failed: {e}")
            raise
    
    def upload_file(self, local_path, remote_path):
        """
        Upload a file to the remote host via SFTP
        
        :param local_path: Local file path
        :param remote_path: Remote destination path
        :return: True if successful
        """
        if not self.sftp:
            raise RuntimeError("SFTP client not initialized")
        
        try:
            local_path = Path(local_path).expanduser()
            self.debug(f"Uploading {local_path} to {remote_path}")
            
            # Create remote directory if needed
            remote_dir = os.path.dirname(remote_path)
            if remote_dir:
                self._ensure_remote_directory(remote_dir)
            
            self.sftp.put(str(local_path), remote_path)
            self.debug(f"File uploaded successfully")
            
            return True
            
        except Exception as e:
            self.debug(f"File upload failed: {e}")
            raise
    
    def download_file(self, remote_path, local_path):
        """
        Download a file from the remote host via SFTP
        
        :param remote_path: Remote file path
        :param local_path: Local destination path
        :return: True if successful
        """
        if not self.sftp:
            raise RuntimeError("SFTP client not initialized")
        
        try:
            local_path = Path(local_path).expanduser()
            self.debug(f"Downloading {remote_path} to {local_path}")
            
            # Ensure local directory exists
            local_path.parent.mkdir(parents=True, exist_ok=True)
            
            self.sftp.get(remote_path, str(local_path))
            self.debug(f"File downloaded successfully")
            
            return True
            
        except Exception as e:
            self.debug(f"File download failed: {e}")
            raise
    
    def file_exists(self, remote_path):
        """
        Check if a file exists on the remote host
        
        :param remote_path: Remote file path
        :return: True if file exists
        """
        if not self.sftp:
            raise RuntimeError("SFTP client not initialized")
        
        try:
            self.sftp.stat(remote_path)
            return True
        except IOError:
            return False
    
    def wait_for_file(self, remote_path, timeout=300, poll_interval=5):
        """
        Wait for a file to exist on the remote host
        
        :param remote_path: Remote file path
        :param timeout: Maximum wait time in seconds
        :param poll_interval: Seconds between checks
        :return: True if file exists, False if timeout
        """
        self.debug(f"Waiting for file {remote_path} (timeout: {timeout}s)")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.file_exists(remote_path):
                self.debug(f"File {remote_path} found")
                return True
            time.sleep(poll_interval)
        
        self.debug(f"Timeout waiting for {remote_path}")
        return False
    
    def _ensure_remote_directory(self, remote_dir):
        """
        Ensure remote directory exists, create if not
        
        :param remote_dir: Remote directory path
        """
        try:
            self.sftp.stat(remote_dir)
        except IOError:
            # Directory doesn't exist, create it
            self.debug(f"Creating remote directory: {remote_dir}")
            self.execute_command(f"mkdir -p {remote_dir}")
    
    def close(self):
        """Close SSH and SFTP connections"""
        try:
            if self.sftp:
                self.sftp.close()
                self.debug("SFTP connection closed")
            
            if self.client:
                self.client.close()
                self.debug("SSH connection closed")
                
        except Exception as e:
            self.debug(f"Error closing connections: {e}")
    
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
