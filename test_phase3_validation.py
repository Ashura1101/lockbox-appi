import json
import uuid
from app_api import app

def run_phase3_tests():
    client = app.test_client()
    test_user = f"user_test_{uuid.uuid4().hex[:8]}"
    test_pass = "TestMasterPass123!"

    print("=" * 60)
    print("EJECUTANDO PRUEBAS DE VALIDACIÓN DE LA FASE 3")
    print("=" * 60)

    # 0. Registro de usuario de prueba
    reg_resp = client.post('/api/register', json={"username": test_user, "master_password": test_pass})
    assert reg_resp.status_code == 201, f"Error en registro: {reg_resp.get_data(as_text=True)}"
    print(f"[OK] Usuario de prueba registrado: {test_user}")

    # PRUEBA 1: Login y generación del par de tokens (Access + Refresh)
    print("\n--- PRUEBA 1: Login & Generación de Tokens ---")
    login_resp = client.post('/api/login', json={"username": test_user, "master_password": test_pass})
    assert login_resp.status_code == 200, f"Login fallido: {login_resp.get_data(as_text=True)}"
    data = login_resp.get_json()
    
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    assert access_token and refresh_token, "No se recibieron los tokens esperados"
    print(f"[OK] Access Token recibido (15 min): {access_token[:25]}...")
    print(f"[OK] Refresh Token recibido (7 días): {refresh_token[:25]}...")

    # PRUEBA 2: Refresh Token Rotativo & Revocación del Token Usado
    print("\n--- PRUEBA 2: Rotación de Refresh Token ---")
    refresh_resp = client.post('/api/auth/refresh', json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 200, f"Refresh fallido: {refresh_resp.get_data(as_text=True)}"
    ref_data = refresh_resp.get_json()
    
    new_access_token = ref_data.get("access_token")
    new_refresh_token = ref_data.get("refresh_token")
    assert new_access_token and new_refresh_token, "No se recibieron los nuevos tokens tras refresh"
    print(f"[OK] Nuevo Access Token emitido: {new_access_token[:25]}...")
    print(f"[OK] Nuevo Refresh Token emitido: {new_refresh_token[:25]}...")

    # Verificar que el refresh_token anterior AHORA ESTÁ REVOCADO
    reuse_resp = client.post('/api/auth/refresh', json={"refresh_token": refresh_token})
    assert reuse_resp.status_code == 401, f"El token antiguo debería ser rechazado pero dio status {reuse_resp.status_code}"
    print(f"[OK] Reuso de Refresh Token antiguo rechazado correctamente (401: {reuse_resp.get_json().get('error')})")

    # PRUEBA 3: Logout & Revocación Completa
    print("\n--- PRUEBA 3: Logout & Revocación de Sesión ---")
    logout_resp = client.post('/api/auth/logout', 
                              headers={"Authorization": f"Bearer {new_access_token}"},
                              json={"refresh_token": new_refresh_token})
    assert logout_resp.status_code == 200, f"Logout fallido: {logout_resp.get_data(as_text=True)}"
    print(f"[OK] Respuesta de Logout (200): {logout_resp.get_json().get('mensaje')}")

    # Verificar que el new_access_token se revocó
    revocation_check = client.post('/api/auth/logout', 
                                    headers={"Authorization": f"Bearer {new_access_token}"},
                                    json={})
    assert revocation_check.status_code == 401, "Access Token revocado debería devolver 401"
    print(f"[OK] Intento de usar Access Token revocado rechazado (401: {revocation_check.get_json().get('error')})")

    # Verificar que el new_refresh_token también se revocó
    refresh_after_logout = client.post('/api/auth/refresh', json={"refresh_token": new_refresh_token})
    assert refresh_after_logout.status_code == 401, "Refresh Token revocado en logout debería devolver 401"
    print(f"[OK] Intento de usar Refresh Token revocado tras logout rechazado (401: {refresh_after_logout.get_json().get('error')})")

    print("\n" + "=" * 60)
    print("¡TODAS LAS PRUEBAS DE VALIDACIÓN DE LA FASE 3 PASARON CON ÉXITO!")
    print("=" * 60)

if __name__ == "__main__":
    run_phase3_tests()
