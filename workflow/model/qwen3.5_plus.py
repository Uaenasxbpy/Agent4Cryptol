from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage

llm = ChatOpenAI(
    model="qwen3.5-plus",
    # glm-5
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# 调用
response = llm.invoke([HumanMessage(content="你好,你是谁？")])
print(response.content)