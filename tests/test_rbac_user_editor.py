import unittest
from app import create_app


class TestRBACUserEditor(unittest.TestCase):
    def setUp(self):
        self.app = create_app({"TESTING": True, "SECRET_KEY": "test-secret"})
        self.client = self.app.test_client()

    def test_default_role_is_editor_for_backward_compatibility(self):
        """Without any session role set, default role is editor for tests and unauthenticated calls."""
        response = self.client.get('/inventory/new')
        self.assertEqual(response.status_code, 200)

    def test_switch_role_endpoint(self):
        """Switching role sets session and redirects."""
        with self.client:
            res = self.client.get('/auth/switch-role/user', follow_redirects=True)
            self.assertEqual(res.status_code, 200)
            from flask import session
            self.assertEqual(session.get('role'), 'user')

            res2 = self.client.get('/auth/switch-role/editor', follow_redirects=True)
            self.assertEqual(res2.status_code, 200)
            self.assertEqual(session.get('role'), 'editor')

    def test_user_role_blocked_from_inventory_creation(self):
        """User role cannot access inventory creation form."""
        with self.client:
            self.client.get('/auth/switch-role/user')
            res = self.client.get('/inventory/new', follow_redirects=False)
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers.get('Location'), '/')

    def test_user_role_blocked_from_kits_creation(self):
        """User role cannot access kits creation form."""
        with self.client:
            self.client.get('/auth/switch-role/user')
            res = self.client.get('/kits/new', follow_redirects=False)
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers.get('Location'), '/')

    def test_user_role_blocked_from_student_registration(self):
        """User role cannot access student registration."""
        with self.client:
            self.client.get('/auth/switch-role/user')
            res = self.client.get('/students/new', follow_redirects=False)
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers.get('Location'), '/')

    def test_user_role_blocked_from_maintenance_creation(self):
        """User role cannot access maintenance work order creation."""
        with self.client:
            self.client.get('/auth/switch-role/user')
            res = self.client.get('/maintenance/new', follow_redirects=False)
            self.assertEqual(res.status_code, 302)
            self.assertEqual(res.headers.get('Location'), '/')

    def test_user_role_blocked_from_transactions_post(self):
        """User role cannot issue or return equipment via POST /transactions."""
        with self.client:
            self.client.get('/auth/switch-role/user')
            res = self.client.post('/transactions', data={
                'action': 'issue',
                'item_code': 'TEST',
                'student_enrolment': 'STU001',
                'quantity': '1',
                'due_date': '2026-10-20'
            }, follow_redirects=False)
            self.assertEqual(res.status_code, 302)
            self.assertIn('/transactions', res.headers.get('Location', ''))

    def test_login_portal_page(self):
        """Login role selection portal renders properly."""
        res = self.client.get('/login')
        self.assertEqual(res.status_code, 200)
        self.assertIn(b'User Mode', res.data)
        self.assertIn(b'Editor Mode', res.data)


if __name__ == '__main__':
    unittest.main()
