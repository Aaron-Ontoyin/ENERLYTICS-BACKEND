"""
Test module for user authentication endpoints.

This module contains comprehensive tests for the user authentication system,
including registration, login, token management, and authorization.
"""

import pytest
from httpx import AsyncClient

from src.apps.users.schemas import UserType


class TestUserAuth:
    """
    Test class for user authentication functionality.

    Tests cover:
    - User registration (normal and admin users)
    - Login with valid and invalid credentials
    - Token-based authentication (access and refresh tokens)
    - User profile retrieval
    - Admin-only endpoint access control
    - Token refresh mechanism
    - Logout functionality for both access and refresh tokens
    """

    @pytest.fixture(autouse=True)
    def setup_data(self):
        """
        Set up test data for user authentication tests.

        Creates sample user data for regular users and admin users
        that will be used across all test methods.
        """
        self.user_data = {
            "email": "test@example.com",
            "key": "testpassword",
            "key_confirm": "testpassword",
            "first_name": "Test",
            "last_name": "User",
        }
        self.admin_data = {
            "email": "admin@example.com",
            "key": "adminpassword",
            "key_confirm": "adminpassword",
            "first_name": "Admin",
            "last_name": "User",
            "type": UserType.ADMIN.value,
        }

    async def test_register_user(self, async_client: AsyncClient):
        """
        Test successful user registration.

        Verifies that:
        - Registration returns 200 status code
        - Response contains user email and ID
        - Sensitive data (hashed_key) is not exposed in response
        """
        response = await async_client.post("/auth/register", json=self.user_data)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == self.user_data["email"]
        assert "id" in data
        assert "hashed_key" not in data

    async def test_register_existing_user(self, async_client: AsyncClient):
        """
        Test registration with an already existing email.

        Verifies that:
        - First registration succeeds
        - Second registration with same email returns 400 error
        - Error message indicates user already exists
        """
        await async_client.post("/auth/register", json=self.user_data)  # First time
        response = await async_client.post(
            "/auth/register", json=self.user_data
        )  # Second time
        assert response.status_code == 400
        assert response.json()["detail"] == "User already exists"

    async def test_login(self, async_client: AsyncClient):
        """
        Test successful user login.

        Verifies that:
        - Login returns 200 status code
        - Response contains both access and refresh tokens
        """
        await async_client.post("/auth/register", json=self.user_data)
        login_data = {"email": self.user_data["email"], "key": self.user_data["key"]}
        response = await async_client.post("/auth/login", json=login_data)
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data

    async def test_login_invalid_credentials(self, async_client: AsyncClient):
        """
        Test login with invalid credentials.

        Verifies that:
        - Login with wrong password returns 401 status code
        - Error message indicates invalid credentials
        """
        await async_client.post("/auth/register", json=self.user_data)
        login_data = {"email": self.user_data["email"], "key": "wrongpassword"}
        response = await async_client.post("/auth/login", json=login_data)
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid credentials"

    async def test_get_me(self, async_client: AsyncClient):
        """
        Test retrieving current user profile.

        Verifies that:
        - Authenticated request returns 200 status code
        - Response contains correct user email
        """
        await async_client.post("/auth/register", json=self.user_data)
        login_data = {"email": self.user_data["email"], "key": self.user_data["key"]}
        login_response = await async_client.post("/auth/login", json=login_data)
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}
        response = await async_client.get("/auth/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == self.user_data["email"]

    async def test_get_users_as_non_admin(self, async_client: AsyncClient):
        """
        Test accessing admin-only endpoint as regular user.

        Verifies that:
        - Non-admin user receives 403 Forbidden status
        - Error message indicates admin access required
        """
        await async_client.post("/auth/register", json=self.user_data)
        login_data = {"email": self.user_data["email"], "key": self.user_data["key"]}
        login_response = await async_client.post("/auth/login", json=login_data)
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.get("/auth/users", headers=headers)
        assert response.status_code == 403
        assert response.json()["detail"] == "Only admin users can access this endpoint"

    async def test_get_users_as_admin(self, async_client: AsyncClient):
        """
        Test accessing admin-only endpoint as admin user.

        Verifies that:
        - Admin user receives 200 status code
        - Response contains paginated user list with items and total count
        - At least one user exists in the response
        """
        await async_client.post("/auth/register", json=self.admin_data)
        login_data = {"email": self.admin_data["email"], "key": self.admin_data["key"]}
        login_response = await async_client.post("/auth/login", json=login_data)
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.get("/auth/users", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) >= 1

    async def test_refresh_token(self, async_client: AsyncClient):
        """
        Test token refresh functionality.

        Verifies that:
        - Refresh token request returns 200 status code
        - Response contains new access token
        - Token type is correctly set to "bearer"
        """
        await async_client.post("/auth/register", json=self.user_data)
        login_data = {"email": self.user_data["email"], "key": self.user_data["key"]}
        login_response = await async_client.post("/auth/login", json=login_data)
        refresh_token = login_response.json()["refresh_token"]

        response = await async_client.post(
            "/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "token_type" in data
        assert data["token_type"] == "bearer"

    async def test_logout_access(self, async_client: AsyncClient):
        """
        Test access token logout functionality.

        Verifies that:
        - Logout request returns 200 status code with success message
        - Access token becomes invalid after logout
        - Subsequent requests with the token return 401 Unauthorized
        """
        await async_client.post("/auth/register", json=self.user_data)
        login_data = {"email": self.user_data["email"], "key": self.user_data["key"]}
        login_response = await async_client.post("/auth/login", json=login_data)
        access_token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {access_token}"}

        response = await async_client.post("/auth/logout-access", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

        me_response = await async_client.get("/auth/me", headers=headers)
        assert me_response.status_code == 401

    async def test_logout_refresh(self, async_client: AsyncClient):
        """
        Test refresh token logout functionality.

        Verifies that:
        - Logout request returns 200 status code with success message
        - Refresh token becomes invalid after logout
        - Subsequent refresh attempts return 401 Unauthorized
        """
        await async_client.post("/auth/register", json=self.user_data)
        login_data = {"email": self.user_data["email"], "key": self.user_data["key"]}
        login_response = await async_client.post("/auth/login", json=login_data)
        refresh_token = login_response.json()["refresh_token"]
        headers = {"Authorization": f"Bearer {refresh_token}"}

        response = await async_client.post("/auth/logout-refresh", headers=headers)
        assert response.status_code == 200
        assert response.json() == {"message": "success"}

        refresh_response = await async_client.post(
            "/auth/refresh", json={"refresh_token": refresh_token}
        )
        assert refresh_response.status_code == 401
