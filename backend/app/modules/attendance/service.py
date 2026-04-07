# backend/app/modules/attendance/service.py
import json
from datetime import datetime, date, timedelta, time, UTC, timezone
from typing import List, Optional, Dict, Any
from app.modules.attendance.models import Attendance
from app.modules.salary.models import LeaveStatus, LeaveRecord
from app.modules.settings.models import AppSetting
from app.modules.users.models import User, UserRole

class AttendanceService:
    @staticmethod
    async def get_setting(key: str, default: str) -> str:
        row = await AppSetting.find_one(AppSetting.key == key)
        return row.value if row and row.value is not None else default

    @staticmethod
    async def get_float_setting(key: str, default: float) -> float:
        raw = await AttendanceService.get_setting(key, str(default))
        try:
            return float(raw)
        except (TypeError, ValueError):
            return default

    @staticmethod
    async def get_list_setting(key: str, default: List[str]) -> List[str]:
        raw = await AttendanceService.get_setting(key, json.dumps(default))
        if not raw:
            return list(default)
        raw = str(raw).strip()
        try:
            val = json.loads(raw)
            if isinstance(val, list):
                return [str(v).strip() for v in val if str(v).strip()]
        except json.JSONDecodeError:
            pass
        return [v.strip() for v in raw.split(',') if v.strip()]

    @staticmethod
    async def load_attendance_settings() -> dict:
        return {
            "absent_hours_threshold":  await AttendanceService.get_float_setting("attendance_absent_hours_threshold", 0.0),
            "half_day_hours_threshold": await AttendanceService.get_float_setting("attendance_half_day_hours_threshold", 4.0),
            "weekly_off_saturday":     await AttendanceService.get_setting("attendance_weekly_off_saturday", "FULL"),
            "weekly_off_sunday":       await AttendanceService.get_setting("attendance_weekly_off_sunday", "FULL"),
            "official_holidays":       await AttendanceService.get_list_setting("attendance_official_holidays", []),
        }

    @staticmethod
    def get_ist_today() -> date:
        return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()

    @staticmethod
    def _day_range(day: date):
        """UTC-aware datetime range for the full calendar day — used for all date field queries."""
        day_start = datetime.combine(day, time.min).replace(tzinfo=UTC)
        day_end   = datetime.combine(day, time.max).replace(tzinfo=UTC)
        return day_start, day_end

    @staticmethod
    def _to_date(val) -> date:
        """Safely convert a datetime or date to a plain date."""
        if isinstance(val, datetime):
            return val.date()
        return val

    @staticmethod
    def is_official_leave(day: date, settings: dict) -> bool:
        weekday = day.weekday()
        if weekday == 5 and (settings.get("weekly_off_saturday") or "").upper() != "NONE":
            return True
        if weekday == 6 and (settings.get("weekly_off_sunday") or "").upper() != "NONE":
            return True
        holidays = set(settings.get("official_holidays") or [])
        return day.isoformat() in holidays

    @staticmethod
    def compute_daily_summary(records: List[Dict[str, Any]], day: date) -> dict:
        total_hours    = 0.0
        first_in       = None
        last_out       = None
        missing_punch_out = False

        for rec in records:
            p_in  = rec.get("punch_in")
            p_out = rec.get("punch_out")
            if p_in:
                if first_in is None or p_in < first_in:
                    first_in = p_in
            if p_out:
                if last_out is None or p_out > last_out:
                    last_out = p_out

            if p_in:
                # Normalize p_in to UTC-aware (MongoDB may store naive datetimes)
                if p_in.tzinfo is None:
                    p_in = p_in.replace(tzinfo=UTC)
                if p_out:
                    end_time = p_out if p_out.tzinfo is not None else p_out.replace(tzinfo=UTC)
                else:
                    missing_punch_out = True
                    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30)))
                    if day < ist_now.date():
                        end_time = datetime.combine(day, time(23, 59, 59), tzinfo=UTC)
                    else:
                        end_time = datetime.now(UTC)

                if p_in.tzinfo is None:
                    p_in = p_in.replace(tzinfo=UTC)
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=UTC)

                duration = max(0.0, (end_time - p_in).total_seconds() / 3600)
                total_hours += duration

        return {
            "total_hours":      total_hours,
            "first_punch_in":   first_in,
            "last_punch_out":   last_out,
            "missing_punch_out": missing_punch_out,
        }

    @staticmethod
    async def reconcile_all_users(start_date: date, end_date: date, settings: dict):
        users = await User.find(User.is_deleted == False, User.role != UserRole.ADMIN).to_list()
        for u in users:
            await AttendanceService.ensure_auto_leaves(u, start_date, end_date, settings)

    @staticmethod
    async def ensure_auto_leaves(user: User, start_date: date, end_date: date, settings: dict):
        today = AttendanceService.get_ist_today()

        # FIX 2: get_motor_collection
        att_coll   = Attendance.get_pymongo_collection()
        leave_coll = LeaveRecord.get_pymongo_collection()

        start_dt, _  = AttendanceService._day_range(start_date)
        _,  end_dt   = AttendanceService._day_range(end_date)

        # FIX 1: range query instead of date equality
        all_att = await att_coll.find({
            "user_id":    user.id,
            "date":       {"$gte": start_dt, "$lte": end_dt},
            "is_deleted": False
        }).to_list(length=1000)

        all_leaves = await leave_coll.find({
            "user_id":    user.id,
            "start_date": {"$lte": end_dt},
            "end_date":   {"$gte": start_dt},
            "is_deleted": False
        }).to_list(length=100)

        att_by_date = {}
        for a in all_att:
            d = AttendanceService._to_date(a["date"])
            att_by_date.setdefault(d, []).append(a)

        day = start_date
        while day <= end_date:
            if day >= today or AttendanceService.is_official_leave(day, settings):
                day += timedelta(days=1)
                continue

            # FIX 4: removed isinstance guard — normalize both sides with _to_date
            has_leave = any(
                AttendanceService._to_date(l["start_date"]) <= day <= AttendanceService._to_date(l["end_date"])
                for l in all_leaves
            )
            if has_leave:
                day += timedelta(days=1)
                continue

            summary = AttendanceService.compute_daily_summary(att_by_date.get(day, []), day)
            if summary["total_hours"] < float(settings.get("half_day_hours_threshold") or 4.0):
                db_leave = LeaveRecord(
                    user_id=user.id,
                    start_date=day,
                    end_date=day,
                    leave_type="UNPAID",
                    day_type="FULL" if summary["total_hours"] <= float(settings.get("absent_hours_threshold") or 0.0) else "HALF",
                    reason=f"Auto leave: {summary['total_hours']:.2f} hrs on {day.isoformat()}",
                    status=LeaveStatus.PENDING,
                )
                await db_leave.insert()
            day += timedelta(days=1)

    @staticmethod
    async def punch_in_out(current_user: User):
        today = AttendanceService.get_ist_today()
        now   = datetime.now(UTC)

        # FIX 1: datetime range instead of date equality
        day_start, day_end = AttendanceService._day_range(today)

        last_record = await Attendance.find(
            Attendance.user_id    == current_user.id,
            Attendance.date       >= day_start,
            Attendance.date       <= day_end,
            Attendance.is_deleted == False
        ).sort("-punch_in").first_or_none()

        # If last record has no punch_out -> PUNCH OUT
        if last_record and last_record.punch_out is None:
            last_record.punch_out = now
            p_in = last_record.punch_in
            if p_in and p_in.tzinfo is None:
                p_in = p_in.replace(tzinfo=UTC)
            diff = now - p_in
            last_record.total_hours = max(0.0, diff.total_seconds() / 3600.0)
            await last_record.save()
            return last_record

        # Otherwise -> NEW PUNCH IN
        new_record = Attendance(
            user_id=current_user.id,
            date=today,
            punch_in=now,
            punch_out=None,
            total_hours=0.0
        )
        await new_record.insert()
        return new_record

    @staticmethod
    async def get_punch_status(current_user: User):
        today = AttendanceService.get_ist_today()
        now   = datetime.now(UTC)

        # FIX 1: datetime range for all today queries
        day_start, day_end = AttendanceService._day_range(today)

        last_record = await Attendance.find(
            Attendance.user_id    == current_user.id,
            Attendance.date       >= day_start,
            Attendance.date       <= day_end,
            Attendance.is_deleted == False
        ).sort("-punch_in").first_or_none()

        is_punched_in = last_record is not None and last_record.punch_out is None

        # FIX 3: last_punch reflects actual last punch event for display
        # Punched in  -> last event = punch_in of current (active) session
        # Punched out -> last event = punch_out of last completed session
        if last_record:
            last_punch = last_record.punch_in if is_punched_in else (last_record.punch_out or last_record.punch_in)
        else:
            last_punch = None

        first_record = await Attendance.find(
            Attendance.user_id    == current_user.id,
            Attendance.date       >= day_start,
            Attendance.date       <= day_end,
            Attendance.is_deleted == False
        ).sort("punch_in").first_or_none()
        first_punch_in = first_record.punch_in if first_record else None

        today_records = await Attendance.find(
            Attendance.user_id    == current_user.id,
            Attendance.date       >= day_start,
            Attendance.date       <= day_end,
            Attendance.is_deleted == False
        ).to_list()

        # Sum all completed (punched-out) sessions only
        today_hours = sum(r.total_hours for r in today_records if r.total_hours)

        # FIX 2: get_pymongo_collection for aggregates
        coll = Attendance.get_pymongo_collection()

        week_ago = today - timedelta(days=7)
        week_start, _ = AttendanceService._day_range(week_ago)
        week_res = await coll.aggregate([
            {"$match": {
                "user_id":    current_user.id,
                "date":       {"$gte": week_start},   # FIX 1: datetime not date
                "is_deleted": False
            }},
            {"$group": {"_id": None, "total": {"$sum": "$total_hours"}}}
        ]).to_list(length=1)
        week_hours = week_res[0]["total"] if week_res else 0.0

        month_start, _ = AttendanceService._day_range(today.replace(day=1))
        month_res = await coll.aggregate([
            {"$match": {
                "user_id":    current_user.id,
                "date":       {"$gte": month_start},  # FIX 1: datetime not date
                "is_deleted": False
            }},
            {"$group": {"_id": None, "total": {"$sum": "$total_hours"}}}
        ]).to_list(length=1)
        month_hours = month_res[0]["total"] if month_res else 0.0

        # completed_hours_secs = finished sessions only
        # frontend adds live elapsed on top when is_punched_in = true
        completed_hours_secs = round(today_hours * 3600)

        if is_punched_in and last_record:
            p_in = last_record.punch_in
            if p_in and p_in.tzinfo is None:
                p_in = p_in.replace(tzinfo=UTC)
            ongoing_secs = (now - p_in).total_seconds()
            today_hours += (ongoing_secs / 3600)

        return {
            "is_punched_in":        is_punched_in,
            "last_punch":           last_punch,
            "last_punch_ts":        last_punch.timestamp() * 1000 if last_punch else None,
            "first_punch_in":       first_punch_in,
            "first_punch_in_ts":    first_punch_in.timestamp() * 1000 if first_punch_in else None,
            "today_hours":          round(today_hours, 4),
            "today_hours_secs":     round(today_hours * 3600),
            "completed_hours_secs": completed_hours_secs,
            "week_hours":           round(week_hours, 2),
            "month_hours":          round(month_hours, 2),
        }

    @staticmethod
    async def get_attendance_logs(date_val: date, user_id: Any):
        # FIX 1: range query — fixes eye icon showing empty even with records
        day_start, day_end = AttendanceService._day_range(date_val)
        logs = await Attendance.find(
            Attendance.user_id    == user_id,
            Attendance.date       >= day_start,
            Attendance.date       <= day_end,
            Attendance.is_deleted == False
        ).sort("punch_in").to_list()
        return logs

    @staticmethod
    async def get_attendance_summary(
        target_user: User | None,
        start_date: Optional[date],
        end_date: Optional[date],
        reconcile: bool,
        current_user: User
    ):
        if not end_date:
            end_date = AttendanceService.get_ist_today()
        if not start_date:
            start_date = end_date - timedelta(days=30)

        settings = await AttendanceService.load_attendance_settings()

        if target_user:
            users_to_report = [target_user]
        else:
            users_to_report = await User.find(User.is_deleted == False, User.role != UserRole.ADMIN).to_list()

        user_ids = [u.id for u in users_to_report]

        # FIX 2: get_pymongo_collection
        att_coll   = Attendance.get_pymongo_collection()
        leave_coll = LeaveRecord.get_pymongo_collection()

        start_dt, _  = AttendanceService._day_range(start_date)
        _,  end_dt   = AttendanceService._day_range(end_date)

        all_att = await att_coll.find({
            "user_id":    {"$in": user_ids},
            "date":       {"$gte": start_dt, "$lte": end_dt},   # FIX 1
            "is_deleted": False
        }).to_list(length=10000)

        all_leaves = await leave_coll.find({
            "user_id":    {"$in": user_ids},
            "start_date": {"$lte": end_dt},
            "end_date":   {"$gte": start_dt},
            "is_deleted": False
        }).to_list(length=2000)

        att_map = {}
        for a in all_att:
            d = AttendanceService._to_date(a["date"])           # FIX — normalize
            att_map.setdefault((a["user_id"], d), []).append(a)

        leave_map = {}
        for l in all_leaves:
            leave_map.setdefault(l["user_id"], []).append(l)

        records     = []
        total_hours = 0.0

        day = start_date
        while day <= end_date:
            for u in users_to_report:
                day_att = att_map.get((u.id, day), [])
                summary = AttendanceService.compute_daily_summary(day_att, day)

                day_status = "PRESENT"
                if AttendanceService.is_official_leave(day, settings):
                    day_status = "OFF"
                elif summary["total_hours"] <= float(settings.get("absent_hours_threshold") or 0.0):
                    day_status = "ABSENT"
                elif summary["total_hours"] < float(settings.get("half_day_hours_threshold") or 4.0):
                    day_status = "HALF"

                day_leave_status = None
                for l in leave_map.get(u.id, []):
                    sd = AttendanceService._to_date(l["start_date"])  # FIX — normalize
                    ed = AttendanceService._to_date(l["end_date"])    # FIX — normalize
                    if sd <= day <= ed:
                        day_leave_status = l.get("status")
                        break

                records.append({
                    "date":           day,
                    "user_id":        u.id,
                    "user_name":      u.name or u.email,
                    "first_punch_in": summary["first_punch_in"],
                    "last_punch_out": summary["last_punch_out"],
                    "total_hours":    summary["total_hours"],
                    "day_status":     day_status,
                    "leave_status":   day_leave_status,
                })
                total_hours += summary["total_hours"]
            day += timedelta(days=1)

        return {
            "start_date":  start_date,
            "end_date":    end_date,
            "total_hours": total_hours,
            "records":     records,
        }