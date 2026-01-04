from typing import List, Dict


class ConversationMemory:
    def __init__(self):
        # Stores conversations like:
        # { "session_id": [ {role, content}, ... ] }
        self.sessions: Dict[str, List[Dict[str, str]]] = {}

    def get_messages(self, session_id: str) -> List[Dict[str, str]]:
        """
        Get conversation history for a session.
        """
        return self.sessions.get(session_id, [])

    def add_message(self, session_id: str, role: str, content: str):
        """
        Add a message to the conversation history.
        """
        if session_id not in self.sessions:
            self.sessions[session_id] = []

        self.sessions[session_id].append(
            {"role": role, "content": content}
        )

    def clear_session(self, session_id: str):
        """
        Clear conversation history for a session.
        """
        if session_id in self.sessions:
            del self.sessions[session_id]


memory = ConversationMemory()
