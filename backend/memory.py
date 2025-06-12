import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
from google.cloud import firestore as gcf

# ✅ Prevent duplicate Firebase initialization
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-service-account.json")
    firebase_admin.initialize_app(cred)

# ✅ Firestore client
db = firestore.client()

# 🔄 Session Management Functions

def get_session(session_id: str):
    """Fetch session data from Firestore"""
    try:
        doc = db.collection("chat_sessions").document(session_id).get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        print(f"[Memory] Error in get_session: {e}")
        return None

def update_session(session_id: str, updates: dict):
    """Update an existing session; create if not found"""
    try:
        doc_ref = db.collection("chat_sessions").document(session_id)
        if not doc_ref.get().exists:
            print(f"[Memory] Creating new session for update: {session_id}")
            data = {
                "created_at": datetime.now(),
                "updated_at": datetime.now(),
                **updates
            }
            doc_ref.set(data)
        else:
            print(f"[Memory] Updating session: {session_id}")
            updates["updated_at"] = datetime.now()
            doc_ref.update(updates)
    except Exception as e:
        print(f"[Memory] Error in update_session: {e}")

def create_new_session(session_id: str, initial_data: dict):
    """Create a new session with initial data"""
    try:
        db.collection("chat_sessions").document(session_id).set(initial_data)
    except Exception as e:
        print(f"[Memory] Error in create_new_session: {e}")

# 🧠 Optional Class for OOP-Based Session Management

class ConversationMemory:
    def __init__(self, user_id):
        self.user_id = user_id
        self.session = self._get_session()

    def _get_session(self):
        """Fetch session from Firestore or create a new one"""
        try:
            doc_ref = db.collection("chat_sessions").document(self.user_id)
            doc = doc_ref.get()
            if doc.exists:
                session = doc.to_dict()
                if datetime.now() - session.get('last_updated', datetime.now()) > timedelta(minutes=30):
                    return self._create_new_session()
                return session
            else:
                return self._create_new_session()
        except Exception as e:
            print(f"[Memory] Error getting session: {e}")
            return self._create_new_session()

    def _create_new_session(self):
        return {
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are a helpful flight booking assistant. Keep responses concise and friendly. Always confirm details before proceeding with bookings.'
                }
            ],
            'context': {
                'origin': None,
                'destination': None,
                'departure_date': None,
                'return_date': None,
                'passengers': None,
                'booking_step': 'initial'
            },
            'last_updated': datetime.now()
        }

    def add_message(self, role, content):
        self.session['messages'].append({
            'role': role,
            'content': content
        })

    def get_messages(self):
        return self.session['messages']

    def get_context(self):
        return self.session.get('context', {})

    def update_context(self, new_context):
        self.session['context'].update(new_context)

    def save(self):
        """Save the current session to Firestore"""
        try:
            self.session['last_updated'] = datetime.now()
            db.collection('chat_sessions').document(self.user_id).set(self.session)
        except Exception as e:
            print(f"[Memory] Error saving session: {e}")
