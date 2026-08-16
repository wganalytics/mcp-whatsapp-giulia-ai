class MessageGiuliaAI:
    def __init__(self, data):
        self.push_name = data.get("push_name", "Unknown")
        self.message_timestamp = data.get("message_timestamp", 0)
        self.message_type = data.get("message_type", "text")
        self.text = data.get("text", "")

    def get_text(self):
        return self.text
