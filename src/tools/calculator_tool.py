"""计算器 MCP 工具 — 执行基本数学运算"""
import re

from claude_agent_sdk import tool


# 只允许数字、运算符、括号、小数点、空格
_SAFE_PATTERN = re.compile(r"^[\d\s+\-*/().%^]+$")


@tool(
    name="calculate",
    description="计算数学表达式的结果。支持加减乘除、幂运算、括号、取余。例如：'2+3*4'、'(10-3)/7'、'2^10'",
    input_schema={"expression": str},
)
async def calculate(args):
    expression = args.get("expression", "").strip()
    if not expression:
        return {"content": [{"type": "text", "text": "请提供数学表达式"}]}
    if not _SAFE_PATTERN.match(expression):
        return {"content": [{"type": "text", "text": f"表达式包含不安全字符，只支持基本数学运算: {expression}"}]}
    try:
        # 将 ^ 替换为 Python 的幂运算符 **
        py_expr = expression.replace("^", "**")
        result = eval(py_expr, {"__builtins__": {}}, {})
        return {"content": [{"type": "text", "text": f"{expression} = {result}"}]}
    except ZeroDivisionError:
        return {"content": [{"type": "text", "text": "错误：除数不能为零"}]}
    except Exception as e:
        return {"content": [{"type": "text", "text": f"计算错误：{e}"}]}
