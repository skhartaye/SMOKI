#!/usr/bin/env python3
"""
Quick syntax test for rpi_stream.py
"""

import sys
import os

def test_syntax():
    """Test if rpi_stream.py has valid Python syntax"""
    try:
        # Add the current directory to Python path
        sys.path.insert(0, os.path.dirname(__file__))
        
        # Try to compile the file
        with open('rpi_stream.py', 'r') as f:
            source = f.read()
        
        compile(source, 'rpi_stream.py', 'exec')
        print("✅ rpi_stream.py syntax is valid")
        return True
        
    except SyntaxError as e:
        print(f"❌ Syntax error in rpi_stream.py:")
        print(f"   Line {e.lineno}: {e.text}")
        print(f"   Error: {e.msg}")
        return False
    except Exception as e:
        print(f"❌ Error testing syntax: {e}")
        return False

if __name__ == '__main__':
    test_syntax()