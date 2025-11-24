#!/usr/bin/env python3
"""
Simple WebSocket test without external dependencies.
Tests WS connection using the standard library only.
"""
import socket
import sys

def test_tcp_connection(host, port):
    """Test basic TCP connectivity"""
    print(f"Testing TCP connection to {host}:{port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((host, port))
        sock.close()
        
        if result == 0:
            print(f"✅ TCP connection to {host}:{port} successful")
            return True
        else:
            print(f"❌ TCP connection to {host}:{port} failed (error code: {result})")
            return False
    except Exception as e:
        print(f"❌ TCP connection failed: {e}")
        return False

def main():
    host = "20.244.35.24"
    
    # Test HTTP port
    http_ok = test_tcp_connection(host, 8000)
    
    # Test DB port (should be blocked externally, but let's check)
    db_ok = test_tcp_connection(host, 5432)
    
    print("\n" + "="*50)
    print("Summary:")
    print(f"  HTTP (8000): {'✅ OPEN' if http_ok else '❌ BLOCKED'}")
    print(f"  DB (5432): {'✅ OPEN' if db_ok else '❌ BLOCKED (expected)'}")
    print("="*50)
    
    if http_ok:
        print("\n🎉 Port 8000 is accessible! WebSocket should work.")
        print("Next: Test with your Flutter app")
        sys.exit(0)
    else:
        print("\n⚠️ Port 8000 is still blocked.")
        print("Please open port 8000 in Azure NSG settings.")
        sys.exit(1)

if __name__ == "__main__":
    main()
