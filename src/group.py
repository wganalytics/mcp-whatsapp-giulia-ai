class Group:
    def __init__(self, group_id, name):
        self.group_id = group_id
        self.name = name

    def __repr__(self):
        return f"Group(id={self.group_id}, name={self.name})"
