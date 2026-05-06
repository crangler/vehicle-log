import sqlite3

from src.utils import DEFAULT_ITEMS


# ── database ───────────────────────────────────────────────────────────────

class DatabaseManager:
    def __init__(self, db_path="vehicles.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()
        self._migrate_per_vehicle_items()
        self._migrate_service_log_images()
        self._migrate_odometer_reading_date()
        self._migrate_parts()
        for v in self.conn.execute("SELECT id FROM vehicles"):
            self._seed_vehicle_maintenance_items(v["id"])

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS vehicles (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                nickname        TEXT,
                year            INTEGER NOT NULL,
                make            TEXT NOT NULL,
                model           TEXT NOT NULL,
                trim            TEXT,
                color           TEXT,
                vin             TEXT,
                license_plate   TEXT,
                current_mileage       INTEGER DEFAULT 0,
                odometer_reading_date TEXT,
                notes                 TEXT,
                date_added            TEXT DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS maintenance_items (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id      INTEGER REFERENCES vehicles(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                interval_miles  INTEGER,
                interval_months INTEGER,
                sort_order      INTEGER DEFAULT 99
            );

            CREATE TABLE IF NOT EXISTS service_log (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id          INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                item_id             INTEGER NOT NULL REFERENCES maintenance_items(id),
                service_date        TEXT NOT NULL,
                mileage_at_service  INTEGER,
                cost                REAL,
                shop                TEXT,
                parts               TEXT,
                notes               TEXT
            );

            CREATE TABLE IF NOT EXISTS parts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id      INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                name            TEXT NOT NULL,
                part_number     TEXT,
                alt_part_number TEXT,
                supplier        TEXT,
                url             TEXT,
                price           REAL,
                notes           TEXT
            );

            CREATE TABLE IF NOT EXISTS part_images (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                part_id   INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                path      TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'image'
            );

            CREATE TABLE IF NOT EXISTS vehicle_images (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                vehicle_id  INTEGER NOT NULL REFERENCES vehicles(id) ON DELETE CASCADE,
                path        TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS service_log_images (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id  INTEGER NOT NULL REFERENCES service_log(id) ON DELETE CASCADE,
                path    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS maintenance_item_files (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id   INTEGER NOT NULL REFERENCES maintenance_items(id) ON DELETE CASCADE,
                path      TEXT NOT NULL,
                file_type TEXT NOT NULL DEFAULT 'image'
            );

            CREATE TABLE IF NOT EXISTS maintenance_item_parts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id  INTEGER NOT NULL REFERENCES maintenance_items(id) ON DELETE CASCADE,
                part_id  INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS service_log_parts (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                log_id   INTEGER NOT NULL REFERENCES service_log(id) ON DELETE CASCADE,
                part_id  INTEGER NOT NULL REFERENCES parts(id) ON DELETE CASCADE,
                quantity INTEGER NOT NULL DEFAULT 1
            );
        """)
        self.conn.commit()

    def _migrate_per_vehicle_items(self):
        cols = {row[1] for row in self.conn.execute(
            "PRAGMA table_info(maintenance_items)")}
        if "vehicle_id" in cols:
            return
        self.conn.execute(
            "ALTER TABLE maintenance_items ADD COLUMN vehicle_id INTEGER REFERENCES vehicles(id) ON DELETE CASCADE"
        )
        global_items = self.conn.execute(
            "SELECT * FROM maintenance_items WHERE vehicle_id IS NULL"
        ).fetchall()
        vehicles = self.conn.execute("SELECT id FROM vehicles").fetchall()
        id_map = {}
        for item in global_items:
            for v in vehicles:
                cur = self.conn.execute(
                    "INSERT INTO maintenance_items (vehicle_id, name, interval_miles, interval_months, sort_order) VALUES (?,?,?,?,?)",
                    (v["id"], item["name"], item["interval_miles"],
                     item["interval_months"], item["sort_order"]),
                )
                id_map[(item["id"], v["id"])] = cur.lastrowid
        for entry in self.conn.execute("SELECT id, vehicle_id, item_id FROM service_log").fetchall():
            new_id = id_map.get((entry["item_id"], entry["vehicle_id"]))
            if new_id:
                self.conn.execute(
                    "UPDATE service_log SET item_id=? WHERE id=?", (new_id, entry["id"]))
        self.conn.execute(
            "DELETE FROM maintenance_items WHERE vehicle_id IS NULL")
        self.conn.commit()

    def _migrate_service_log_images(self):
        cols = {row[1] for row in self.conn.execute(
            "PRAGMA table_info(service_log_images)")}
        if "file_type" not in cols:
            self.conn.execute(
                "ALTER TABLE service_log_images ADD COLUMN file_type TEXT NOT NULL DEFAULT 'image'"
            )
            self.conn.commit()

    def _migrate_odometer_reading_date(self):
        cols = {row[1]
                for row in self.conn.execute("PRAGMA table_info(vehicles)")}
        if "odometer_reading_date" not in cols:
            self.conn.execute(
                "ALTER TABLE vehicles ADD COLUMN odometer_reading_date TEXT")
            self.conn.commit()

    def _migrate_parts(self):
        cols = {row[1]
                for row in self.conn.execute("PRAGMA table_info(parts)")}
        if "notes" not in cols:
            self.conn.execute("ALTER TABLE parts ADD COLUMN notes TEXT")
            self.conn.commit()

    def _seed_vehicle_maintenance_items(self, vehicle_id):
        if self.conn.execute(
            "SELECT COUNT(*) FROM maintenance_items WHERE vehicle_id=?", (vehicle_id,)
        ).fetchone()[0] == 0:
            self.conn.executemany(
                "INSERT INTO maintenance_items (vehicle_id, name, interval_miles, interval_months, sort_order) VALUES (?,?,?,?,?)",
                [(vehicle_id, name, dist, months, order)
                 for name, dist, months, order in DEFAULT_ITEMS],
            )
            self.conn.commit()

    # vehicles

    def add_vehicle(self, data):
        cur = self.conn.execute("""
            INSERT INTO vehicles
                (nickname, year, make, model, trim, color, vin, license_plate, current_mileage, odometer_reading_date, notes)
            VALUES
                (:nickname, :year, :make, :model, :trim, :color, :vin, :license_plate, :current_mileage, :odometer_reading_date, :notes)
        """, data)
        self.conn.commit()
        self._seed_vehicle_maintenance_items(cur.lastrowid)

    def update_vehicle(self, vehicle_id, data):
        self.conn.execute("""
            UPDATE vehicles
            SET nickname=:nickname, year=:year, make=:make, model=:model,
                trim=:trim, color=:color, vin=:vin, license_plate=:license_plate,
                current_mileage=:current_mileage, odometer_reading_date=:odometer_reading_date,
                notes=:notes
            WHERE id=:id
        """, {**data, "id": vehicle_id})
        self.conn.commit()

    def delete_vehicle(self, vehicle_id):
        self.conn.execute("DELETE FROM vehicles WHERE id=?", (vehicle_id,))
        self.conn.commit()

    def get_all_vehicles(self):
        return self.conn.execute(
            "SELECT * FROM vehicles ORDER BY year DESC, make, model"
        ).fetchall()

    def get_vehicle(self, vehicle_id):
        return self.conn.execute(
            "SELECT * FROM vehicles WHERE id=?", (vehicle_id,)
        ).fetchone()

    # maintenance items

    def get_maintenance_items(self, vehicle_id):
        return self.conn.execute(
            "SELECT * FROM maintenance_items WHERE vehicle_id=? ORDER BY sort_order, name",
            (vehicle_id,),
        ).fetchall()

    def get_maintenance_item(self, item_id: int) -> sqlite3.Row | None:
        return self.conn.execute(
            "SELECT * FROM maintenance_items WHERE id=?", (item_id,)
        ).fetchone()

    def add_maintenance_item(self, vehicle_id, data) -> int:
        max_order = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM maintenance_items WHERE vehicle_id=?",
            (vehicle_id,),
        ).fetchone()[0]
        cur = self.conn.execute(
            """INSERT INTO maintenance_items (vehicle_id, name, interval_miles, interval_months, sort_order)
               VALUES (:vehicle_id, :name, :interval_miles, :interval_months, :sort_order)""",
            {**data, "vehicle_id": vehicle_id, "sort_order": max_order + 1},
        )
        self.conn.commit()
        return cur.lastrowid

    def update_maintenance_item(self, item_id, data):
        self.conn.execute(
            """UPDATE maintenance_items
               SET name=:name, interval_miles=:interval_miles, interval_months=:interval_months
               WHERE id=:id""",
            {**data, "id": item_id},
        )
        self.conn.commit()

    def delete_maintenance_item(self, item_id):
        self.conn.execute(
            "DELETE FROM service_log WHERE item_id=?", (item_id,))
        self.conn.execute(
            "DELETE FROM maintenance_items WHERE id=?", (item_id,))
        self.conn.commit()

    def get_maintenance_item_files(self, item_id):
        return self.conn.execute(
            "SELECT * FROM maintenance_item_files WHERE item_id=? ORDER BY id", (
                item_id,)
        ).fetchall()

    def add_maintenance_item_file(self, item_id, path, file_type='image'):
        self.conn.execute(
            "INSERT INTO maintenance_item_files (item_id, path, file_type) VALUES (?, ?, ?)",
            (item_id, path, file_type),
        )
        self.conn.commit()

    def delete_maintenance_item_file(self, file_id):
        self.conn.execute(
            "DELETE FROM maintenance_item_files WHERE id=?", (file_id,))
        self.conn.commit()

    def get_maintenance_item_parts(self, item_id):
        return self.conn.execute("""
            SELECT mip.id, mip.item_id, mip.part_id, mip.quantity,
                   p.name, p.part_number
            FROM maintenance_item_parts mip
            JOIN parts p ON mip.part_id = p.id
            WHERE mip.item_id = ?
            ORDER BY p.name
        """, (item_id,)).fetchall()

    def set_maintenance_item_parts(self, item_id, parts):
        self.conn.execute(
            "DELETE FROM maintenance_item_parts WHERE item_id=?", (item_id,))
        for p in parts:
            self.conn.execute(
                "INSERT INTO maintenance_item_parts (item_id, part_id, quantity) VALUES (?,?,?)",
                (item_id, p["part_id"], p["quantity"]),
            )
        self.conn.commit()

    def get_service_log_parts(self, log_id):
        return self.conn.execute("""
            SELECT slp.id, slp.log_id, slp.part_id, slp.quantity,
                   p.name, p.part_number
            FROM service_log_parts slp
            JOIN parts p ON slp.part_id = p.id
            WHERE slp.log_id = ?
            ORDER BY p.name
        """, (log_id,)).fetchall()

    def get_service_log_parts_for_entries(
        self, log_ids: list[int]
    ) -> dict[int, list[sqlite3.Row]]:
        if not log_ids:
            return {}
        placeholders = ",".join("?" * len(log_ids))
        rows = self.conn.execute(f"""
            SELECT slp.id, slp.log_id, slp.part_id, slp.quantity,
                   p.name, p.part_number
            FROM service_log_parts slp
            JOIN parts p ON slp.part_id = p.id
            WHERE slp.log_id IN ({placeholders})
            ORDER BY slp.log_id, p.name
        """, log_ids).fetchall()
        result: dict[int, list[sqlite3.Row]] = {}
        for row in rows:
            result.setdefault(row["log_id"], []).append(row)
        return result

    def set_service_log_parts(self, log_id, parts):
        self.conn.execute(
            "DELETE FROM service_log_parts WHERE log_id=?", (log_id,))
        for p in parts:
            self.conn.execute(
                "INSERT INTO service_log_parts (log_id, part_id, quantity) VALUES (?,?,?)",
                (log_id, p["part_id"], p["quantity"]),
            )
        self.conn.commit()

    def get_service_log_count_for_item(self, item_id) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM service_log WHERE item_id=?", (item_id,)
        ).fetchone()[0]

    # parts

    def get_all_parts(self, vehicle_id=None):
        if vehicle_id is None:
            return self.conn.execute(
                "SELECT * FROM parts ORDER BY vehicle_id, name"
            ).fetchall()
        return self.conn.execute(
            "SELECT * FROM parts WHERE vehicle_id=? ORDER BY name", (vehicle_id,)
        ).fetchall()

    def get_part(self, part_id):
        return self.conn.execute(
            "SELECT * FROM parts WHERE id=?", (part_id,)
        ).fetchone()

    def add_part(self, data) -> int:
        cur = self.conn.execute("""
            INSERT INTO parts (vehicle_id, name, part_number, alt_part_number, supplier, url, price, notes)
            VALUES (:vehicle_id, :name, :part_number, :alt_part_number, :supplier, :url, :price, :notes)
        """, data)
        self.conn.commit()
        return cur.lastrowid

    def update_part(self, part_id, data):
        self.conn.execute("""
            UPDATE parts
            SET vehicle_id=:vehicle_id, name=:name, part_number=:part_number,
                alt_part_number=:alt_part_number, supplier=:supplier, url=:url, price=:price,
                notes=:notes
            WHERE id=:id
        """, {**data, "id": part_id})
        self.conn.commit()

    def delete_part(self, part_id):
        self.conn.execute("DELETE FROM parts WHERE id=?", (part_id,))
        self.conn.commit()

    def get_part_images(self, part_id):
        return self.conn.execute(
            "SELECT * FROM part_images WHERE part_id=? ORDER BY id", (part_id,)
        ).fetchall()

    def add_part_image(self, part_id, path, file_type='image'):
        self.conn.execute(
            "INSERT INTO part_images (part_id, path, file_type) VALUES (?, ?, ?)",
            (part_id, path, file_type),
        )
        self.conn.commit()

    def delete_part_image(self, image_id):
        self.conn.execute("DELETE FROM part_images WHERE id=?", (image_id,))
        self.conn.commit()

    # vehicle images

    def get_vehicle_images(self, vehicle_id):
        return self.conn.execute(
            "SELECT * FROM vehicle_images WHERE vehicle_id=? ORDER BY id", (
                vehicle_id,)
        ).fetchall()

    def add_vehicle_image(self, vehicle_id, path):
        self.conn.execute(
            "INSERT INTO vehicle_images (vehicle_id, path) VALUES (?, ?)", (
                vehicle_id, path)
        )
        self.conn.commit()

    def delete_vehicle_image(self, image_id):
        self.conn.execute("DELETE FROM vehicle_images WHERE id=?", (image_id,))
        self.conn.commit()

    # service log images

    def get_service_log_entries(self, vehicle_id):
        return self.conn.execute("""
            SELECT sl.*, mi.name AS service_name
            FROM service_log sl
            JOIN maintenance_items mi ON sl.item_id = mi.id
            WHERE sl.vehicle_id = ?
            ORDER BY sl.service_date DESC, sl.id DESC
        """, (vehicle_id,)).fetchall()

    def get_service_log_entries_range(self, vehicle_id, date_from: str, date_to: str):
        return self.conn.execute("""
            SELECT sl.*, mi.name AS service_name
            FROM service_log sl
            JOIN maintenance_items mi ON sl.item_id = mi.id
            WHERE sl.vehicle_id = ? AND sl.service_date BETWEEN ? AND ?
            ORDER BY sl.service_date ASC, sl.id ASC
        """, (vehicle_id, date_from, date_to)).fetchall()

    def get_service_log_images(self, log_id):
        return self.conn.execute(
            "SELECT * FROM service_log_images WHERE log_id=? ORDER BY id", (
                log_id,)
        ).fetchall()

    def add_service_log_image(self, log_id, path, file_type='image'):
        self.conn.execute(
            "INSERT INTO service_log_images (log_id, path, file_type) VALUES (?, ?, ?)",
            (log_id, path, file_type),
        )
        self.conn.commit()

    def delete_service_log_image(self, image_id):
        self.conn.execute(
            "DELETE FROM service_log_images WHERE id=?", (image_id,))
        self.conn.commit()

    # schedule

    def get_schedule(self, vehicle_id):
        vehicle = self.get_vehicle(vehicle_id)
        items = self.get_maintenance_items(vehicle_id)

        # Fetch all service log entries for this vehicle in one query, most
        # recent first.  The dict comprehension keeps only the first (latest)
        # entry seen per item_id, which is equivalent to the previous LIMIT 1
        # per-item query.
        all_entries = self.conn.execute("""
            SELECT * FROM service_log
            WHERE vehicle_id = ?
            ORDER BY service_date DESC, mileage_at_service DESC
        """, (vehicle_id,)).fetchall()

        last_by_item: dict[int, sqlite3.Row] = {}
        for entry in all_entries:
            if entry["item_id"] not in last_by_item:
                last_by_item[entry["item_id"]] = entry

        return [(item, last_by_item.get(item["id"]), vehicle) for item in items]

    # service log

    def log_service(self, data) -> int:
        cur = self.conn.execute("""
            INSERT INTO service_log
                (vehicle_id, item_id, service_date, mileage_at_service, cost, shop, parts, notes)
            VALUES
                (:vehicle_id, :item_id, :service_date, :mileage_at_service, :cost, :shop, :parts, :notes)
        """, data)
        self.conn.commit()
        return cur.lastrowid

    def get_service_log_entry(self, log_id):
        return self.conn.execute(
            "SELECT * FROM service_log WHERE id=?", (log_id,)
        ).fetchone()

    def update_service_log(self, log_id, data):
        self.conn.execute("""
            UPDATE service_log
            SET vehicle_id=:vehicle_id, item_id=:item_id, service_date=:service_date,
                mileage_at_service=:mileage_at_service, cost=:cost, shop=:shop,
                parts=:parts, notes=:notes
            WHERE id=:id
        """, {**data, "id": log_id})
        self.conn.commit()

    def close(self):
        self.conn.close()
