import pytest
from app.services.conversation_controller import ConversationController

def test_detect_future_action_promise():
    cases = [
        # Promises
        ("Please hold on while I fetch the pictures for you.", True),
        ("I will send it shortly", True),
        ("sending pictures now", True),
        ("wait a moment sir", True),
        ("tasveer bhejta hoon", True),
        ("main abhi tasveer bhej rahi hoon", True),
        ("tasveer bhej deiti hoon", True),
        ("wait karain", True),
        ("wait karein, main bhejta hoon", True),
        ("تصویریں بھیج رہا ہوں", True),
        ("تھوڑا انتظار کریں", True),
        
        # Safe statements
        ("Here is the picture.", False),
        ("This shirt looks great.", False),
        ("We don't have this picture.", False),
        ("Yeh tasveer hai", False),
        ("Sorry, picture available nahi hai", False),
        ("تصویر موجود نہیں", False)
    ]
    
    for message, expected in cases:
        assert ConversationController._detect_future_action_promise(message) == expected, f"Failed on '{message}'"
