import langchain_core
import sys

print(f"langchain_core location: {langchain_core.__file__}")
print("sys.path:")
for p in sys.path:
    print(p)
