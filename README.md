# Skelas — Academic Course Scheduling System

Backend scheduling engine untuk jadwal kuliah universitas. Berbasis Constraint
Satisfaction Problem (CSP) yang diselesaikan dengan OR-Tools CP-SAT.

Detail lengkap ada di [PRD.md](PRD.md), rencana eksekusi di [TASKS.md](TASKS.md).

---

## Status

| Phase | Isi | Status |
|---|---|---|
| 1 | Data modeling & input validation | Selesai |
| 2 | Scheduling engine (CP-SAT) | Selesai |
| 3 | Testing & validation | Selesai |
| 4 | Database & API | Belum |
| 5 | Dashboard/UI | Belum |

---

## Cara Pakai

```bash
pip install -r requirements.txt

python validate.py            # validasi data input
python run_scheduler.py       # generate jadwal → schedule.json
python validate_schedule.py schedule.json   # validasi independen

python -m unittest tests.test_scheduler      # 12 unit test
python tests/benchmark.py                    # benchmark 10/25/50/80 courses
```

---

## Struktur

```
├── data/                  # 8 file JSON (courses, dosen, ruang, dll)
├── src/
│   ├── models/            # dataclass per entitas
│   ├── validation/        # validator data input
│   ├── data_loader.py     # load + lookup maps
│   ├── scheduler.py       # engine CP-SAT
│   └── utils.py           # generator blok slot konsekutif
├── tests/
│   ├── test_scheduler.py  # 12 unit test
│   ├── benchmark.py       # benchmark deterministik
│   └── diagnose_bench.py  # cek kapasitas saat INFEASIBLE
├── run_scheduler.py       # CLI scheduler
├── validate.py            # CLI validasi data
└── validate_schedule.py   # CLI validasi jadwal (independen)
```

---

## Masalah yang Diselesaikan

Cari kombinasi **matkul × dosen × kelompok mahasiswa × hari × slot konsekutif ×
ruang** yang memenuhi 7 hard constraint:

1. Dosen tidak boleh mengajar 2 kelas bersamaan
2. Kelompok mahasiswa tidak boleh punya 2 kelas bersamaan
3. Ruang tidak boleh dipakai 2 kelas bersamaan
4. Kelas hanya boleh di slot availability dosen
5. Ruang harus sesuai tipe (mis. lab komputer butuh COMPUTER_LAB)
6. N SKS = N slot konsekutif (tanpa melompati jam istirahat)
7. Satu kelas tidak boleh dipotong lintas hari

**Prinsip penting**: konflik mahasiswa ditentukan `student_groups`, bukan
`curriculum_semester` — mahasiswa semester 3 boleh ambil matkul semester 5.

---

## Cara Kerja Engine

### Timeline encoding

Setiap kelas jadi satu interval pada timeline absolut:

```
T = day * 10 + offset(slot)

slot pagi 1-5  → offset 0-4
slot siang 6-9 → offset 6-9
offset 5       → jam istirahat, tak pernah terisi
```

1 hari = 10 unit, 1 minggu = 60 unit. Matkul N SKS = interval `[start, start+N)`.

### Constraint encoding (AddNoOverlap)

Konflik tidak dibandingkan per pasangan (pairwise), tapi lewat primitive native
CP-SAT `AddNoOverlap`:

- **Dosen** → kelompokkan interval per dosen → `AddNoOverlap`
- **Mahasiswa** → kelompokkan interval per kelompok → `AddNoOverlap`
- **Ruang** → optional interval per (kelas, ruang kompatibel), presence bool
  terikat variabel ruang → `AddNoOverlap` per ruang

Solver memproses `AddNoOverlap` dengan propagator khusus — jauh lebih efisien
dari ratusan ribu clause bool buatan sendiri.

### Objective (soft)

```
Minimize 100*jumlah_hari + 10*sum(hari) + sum(index_slot)
```

Jadwal sering mungkin (sedikit hari), hari paling awal (Senin dulu), mulai
paling awal dalam hari.

---

## Benchmark

Seed deterministik `SSEED = 20261003`, timeout solver 120s, tiap hasil FEASIBLE
dicek ulang validator independen.

| Courses | Dosen | Ruang | Constraints | Waktu | Status | Valid |
|---|---|---|---|---|---|---|
| 10 | 5 | 4 | 743 | 0.18s | FEASIBLE | VALID |
| 25 | 8 | 6 | 1,586 | 3.84s | FEASIBLE | VALID |
| 50 | 12 | 8 | 3,513 | 120.30s | FEASIBLE | VALID |
| 80 | 16 | 8 | 5,648 | 120.29s | FEASIBLE | VALID |

Dampak refactor pairwise → `AddNoOverlap` (commit `d44e353`):

| Courses | Sebelum | Sesudah |
|---|---|---|
| 10 | 8,248 | 743 |
| 25 | 91,749 | 1,586 |
| 50 | 488,612 | 3,513 |
| 80 | 1,397,302 → **UNKNOWN** (timeout) | 5,648 → **FEASIBLE + VALID** |

Constraint turun ~250x di 80 courses. 50/80 mendekati batas 120s karena solver
masih meng-optimize objective, bukan karena cari feasible-nya lama.

---

## Testing

**12 unit test** (`tests/test_scheduler.py`) — semua pass:

- 3 conflict (dosen, ruang, mahasiswa) + 2 negatif (beda kelompok BOLEH overlap)
- Konflik lintas-semester (IF-3 vs IF-5 yang sama-sama diikut IF-5)
- Slot konsekutif 4 SKS (valid [1-4], [2-5], [6-9]; tak boleh lintas istirahat)
- Availability dosen (hari saja + gap istirahat → INFEASIBLE)
- Tipe ruang (kelas lab → COMPUTER_LAB)
- Skenario INFEASIBLE (10 matkul × 4 SKS, 1 ruang → INFEASIBLE)

**Validator independen** (`validate_schedule.py`) — Python murni, tak percaya
solver. Re-run semua hard constraint di atas `schedule.json`. Exit 0 valid,
exit 1 invalid.

---

## Bug & Insight yang Ditemukan Selama Pengembangan

1. **`OnlyEnforceIf` satu arah** — `AddBoolAnd([...]).OnlyEnforceIf(x)` hanya
   meng-encode `x → AND`, bukan `AND → x`. Tanpa reverse clause, constraint jadi
   vacuous. Semua variabel bool perlu case True dan False.
2. **Semua kelas mulai 08:15 di ruang sama** — akar masalahnya constraint room
   conflict vacuous (bug di atas). Butuh beberapa iterasi untuk menemukannya.
3. **Jadwal menyebar 5 hari padahal 2 cukup** — tak ada objective. Ditambah
   objective, lalu tie-break hari awal (Senin > Jumat).
4. **Benchmark 50/80 INFEASIBLE** — generator bikin availability random yang
   tak muat blok mana pun; 1 dosen rusak membunuh seluruh jadwal. Diperbaiki
   dengan load balancing + ≥2 hari penuh per dosen.
5. **Pairwise encoding meledak** — O(n²) pasangan × beberapa clause = 1.4 juta
   constraint di 80 courses, solver timeout. Diganti `AddNoOverlap` → 5,648.

---

## Roadmap

- **Phase 4**: migrasi JSON → PostgreSQL, FastAPI endpoints, integrasi DB
- **Phase 5**: dashboard CRUD + trigger scheduler + visualisasi jadwal
- Soft constraints berikutnya: preferensi dosen, distribusi merata, gap antar kelas
- Conflict explanation / constraint diagnosis saat INFEASIBLE (PRD §16)
- Constraint relaxation bertingkat (PRD §17)
