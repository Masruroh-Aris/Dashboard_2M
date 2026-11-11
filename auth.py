"""Autentikasi opsional untuk dasbor yang ditanam (embed) di admin web.

Mengapa perlu: URL dasbor yang dapat dibuka tanpa login melewati RBAC admin web (branch admin cabang A bisa melihat cabang B).
Cara kerja: backend admin web menerbitkan JWT HS256 berumur pendek; dasbor memverifikasinya dan MEMBATASI cabang dari klaim token,
bukan dari input pengguna. Bila DASH_JWT_SECRET tidak diatur, dasbor berjalan MODE DEMO tanpa autentikasi (hanya untuk data sintetis).
Klaim: role = super_admin | branch_admin ; branch_id (wajib untuk branch_admin, harus sama dengan nilai kolom cabang_id) ; exp (wajib).
"""
import time

import jwt

PERAN_VALID = ("super_admin", "branch_admin")


class ErrorAuth(Exception):
    pass


def verifikasi(token, secret):
    if not token:
        raise ErrorAuth("Token akses tidak ada. Buka dasbor dari dalam admin web.")
    try:
        klaim = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "role"]})
    except jwt.ExpiredSignatureError:
        raise ErrorAuth("Token kedaluwarsa. Muat ulang halaman dasbor dari admin web.")
    except jwt.InvalidTokenError:
        raise ErrorAuth("Token tidak valid.")
    if klaim["role"] not in PERAN_VALID:
        raise ErrorAuth("Peran tidak diizinkan melihat dasbor.")
    if klaim["role"] == "branch_admin" and not klaim.get("branch_id"):
        raise ErrorAuth("Token branch_admin tidak memuat branch_id.")
    return klaim


def cabang_diizinkan(klaim, semua_cabang):
    """Daftar cabang yang boleh dilihat. super_admin: semua; branch_admin: hanya cabangnya."""
    if klaim is None:
        return sorted(semua_cabang)
    if klaim["role"] == "super_admin":
        return sorted(semua_cabang)
    return [c for c in sorted(semua_cabang) if c == str(klaim["branch_id"]).strip().upper()]


def buat_token(secret, role, branch_id=None, detik=600):
    """Pembantu untuk uji/pengembangan. Di produksi, token diterbitkan oleh backend admin web."""
    klaim = {"role": role, "exp": int(time.time()) + detik}
    if branch_id is not None:
        klaim["branch_id"] = branch_id
    return jwt.encode(klaim, secret, algorithm="HS256")
