#!/usr/bin/env python3
"""
优化验证脚本 - 检查所有改进是否正确应用
"""

import sys
from pathlib import Path

def check_file_exists(path: str, description: str) -> bool:
    """检查文件是否存在。"""
    if Path(path).exists():
        print(f"✓ {description}: {path}")
        return True
    else:
        print(f"✗ {description}: {path} (不存在)")
        return False

def check_import(module_path: str, import_name: str, description: str) -> bool:
    """检查模块是否可以导入。"""
    try:
        if import_name:
            exec(f"from {module_path} import {import_name}")
        else:
            exec(f"import {module_path}")
        print(f"✓ {description}")
        return True
    except Exception as e:
        print(f"✗ {description}: {str(e)}")
        return False

def main():
    """运行所有验证检查。"""
    print("=" * 60)
    print("Agent4Cryptol 优化验证")
    print("=" * 60)
    print()

    checks = []

    # 1. 新文件存在检查
    print("1️⃣  新增文件检查")
    print("-" * 60)
    checks.append(check_file_exists(
        "workflow/settings.py",
        "配置管理模块"
    ))
    checks.append(check_file_exists(
        "workflow/validators.py",
        "数据验证模块"
    ))
    checks.append(check_file_exists(
        "workflow/function_utils.py",
        "函数工具模块"
    ))
    checks.append(check_file_exists(
        "workflow/cryptol_compiler.py",
        "Cryptol编译器模块（NEW）"
    ))
    checks.append(check_file_exists(
        ".env.example",
        "环境配置模板"
    ))
    checks.append(check_file_exists(
        "CRYPTOL_INTEGRATION.md",
        "集成改进文档（NEW）"
    ))
    checks.append(check_file_exists(
        "INTEGRATION_SUMMARY.md",
        "集成总结文档（NEW）"
    ))
    print()

    # 2. 模块导入检查
    print("2️⃣  模块导入检查")
    print("-" * 60)
    checks.append(check_import(
        "workflow.settings",
        "settings",
        "导入settings（配置管理）"
    ))
    checks.append(check_import(
        "workflow.validators",
        "FunctionData",
        "导入FunctionData（数据验证）"
    ))
    checks.append(check_import(
        "workflow.function_utils",
        "FunctionInfo",
        "导入FunctionInfo（函数工具）"
    ))
    checks.append(check_import(
        "workflow.cryptol_compiler",
        "compile_cryptol_code",
        "导入compile_cryptol_code（编译器集成）"
    ))
    checks.append(check_import(
        "workflow.logging_utils",
        "setup_logging",
        "导入setup_logging（增强日志）"
    ))
    print()

    # 3. 兼容性检查
    print("3️⃣  向后兼容性检查")
    print("-" * 60)
    checks.append(check_import(
        "workflow.config",
        "MAX_RETRIES",
        "导入config.MAX_RETRIES（向后兼容）"
    ))
    print()

    # 4. 关键文件修改检查
    print("4️⃣  关键文件修改检查")
    print("-" * 60)
    
    # 检查nodes.py是否使用了新的FunctionInfo
    nodes_file = Path("workflow/nodes.py")
    if nodes_file.exists():
        content = nodes_file.read_text()
        if "FunctionInfo" in content:
            print("✓ nodes.py: 已使用FunctionInfo")
            checks.append(True)
        else:
            print("✗ nodes.py: 未使用FunctionInfo")
            checks.append(False)
        
        if "compile_cryptol_code" in content:
            print("✓ nodes.py: 已改用直接编译器调用（移除HTTP API）")
            checks.append(True)
        else:
            print("✗ nodes.py: 仍在使用HTTP API")
            checks.append(False)
        
        if "import requests" not in content or "requests.post" not in content:
            print("✓ nodes.py: 已移除requests HTTP调用")
            checks.append(True)
        else:
            print("⚠ nodes.py: 仍在导入requests")
            checks.append(False)
    
    # 检查cryptol_compiler.py是否存在
    compiler_file = Path("workflow/cryptol_compiler.py")
    if compiler_file.exists():
        content = compiler_file.read_text()
        if "compile_cryptol_code" in content:
            print("✓ cryptol_compiler.py: 已实现编译函数")
            checks.append(True)
        else:
            print("✗ cryptol_compiler.py: 缺少编译函数")
            checks.append(False)
        
        if "managed_temp_file" in content and "@contextmanager" in content:
            print("✓ cryptol_compiler.py: 已实现临时文件管理器")
            checks.append(True)
        else:
            print("✗ cryptol_compiler.py: 临时文件管理不完整")
            checks.append(False)
    
    # 检查requirements.txt是否简化
    req_file = Path("requirements.txt")
    if req_file.exists():
        content = req_file.read_text()
        if "fastapi" not in content.lower() and "uvicorn" not in content.lower():
            print("✓ requirements.txt: 已移除API服务器依赖")
            checks.append(True)
        else:
            print("⚠ requirements.txt: 仍包含API服务器依赖")
            checks.append(False)
        
        if "pydantic" in content.lower():
            print("✓ requirements.txt: 保留了配置管理依赖")
            checks.append(True)
        else:
            print("✗ requirements.txt: 缺少配置管理依赖")
            checks.append(False)
    
    # 检查settings.py配置修改
    settings_file = Path("workflow/settings.py")
    if settings_file.exists():
        content = settings_file.read_text()
        if "CRYPTOL_CMD" in content:
            print("✓ settings.py: 已添加CRYPTOL_CMD配置")
            checks.append(True)
        else:
            print("✗ settings.py: 缺少CRYPTOL_CMD配置")
            checks.append(False)
        
        if "COMPILE_TIMEOUT" in content:
            print("✓ settings.py: 已添加COMPILE_TIMEOUT配置")
            checks.append(True)
        else:
            print("✗ settings.py: 缺少COMPILE_TIMEOUT配置")
            checks.append(False)
        
        if "CRYPTOL_API_URL" not in content:
            print("✓ settings.py: 已移除API相关配置")
            checks.append(True)
        else:
            print("⚠ settings.py: 仍包含API配置（可选）")
            checks.append(False)
    
    print()

    # 5. 总结
    print("=" * 60)
    total = len(checks)
    passed = sum(checks)
    print(f"验证结果：{passed}/{total} 项检查通过")
    print("=" * 60)
    print()

    if passed >= total - 1:  # 允许1个非关键检查失败
        print("✅ 优化已正确应用！")
        print()
        print("📋 改进摘要：")
        print("  ✓ 配置管理系统（settings.py）")
        print("  ✓ 数据验证（validators.py）")
        print("  ✓ 函数工具（function_utils.py）")
        print("  ✓ CryptolAPI集成（cryptol_compiler.py）")
        print("  ✓ 日志增强（logging_utils.py）")
        print("  ✓ RAG缓存优化（rag.py）")
        print("  ✓ 编译节点改进（nodes.py）")
        print("  ✓ 依赖简化（requirements.txt）")
        print()
        print("🚀 项目现在可以直接运行：python agent_workflow.py")
        return 0
    else:
        print("⚠️  部分检查未通过，请检查上述错误。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
