import random
from skills.base import Skill

JOKES = [
    "为什么程序员总是分不清万圣节和圣诞节？因为 Oct 31 = Dec 25。",
    "一个 SQL 语句走进酒吧，看到两张 table，问：Can I join you?",
    "世界上有 10 种人，懂二进制的和不懂的。",
    "为什么 Java 程序员戴眼镜？因为他们看不见 C#。",
    "一个 bug 走进代码里，开发者说：这不是 bug，这是 feature。",
    "我问 AI 你觉得人类怎么样，它说：正在思考...正在思考...正在思考...",
    "为什么程序员不喜欢户外？因为有太多 bug。",
    "TCP 的三次握手走进酒吧，服务员说：你好。他说：你好。服务员说：你好。他说：好的。",
    "老板问：这个项目还需要多久？程序员说：差不多 10 天。老板说：那给你两个月够吗？程序员：够了够了。",
]

class JokeSkill(Skill):
    name = "joke"
    description = "随机返回一个冷笑话"

    def get_commands(self):
        return {
            "/joke": self.get_joke,
        }

    async def get_joke(self, message):
        return random.choice(JOKES)