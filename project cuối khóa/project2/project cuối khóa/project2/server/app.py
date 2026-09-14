from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd

app = Flask(__name__)
CORS(app)

DATA_PATH = "../data/cad_vnd_exchange_rate.csv"


def load_data():
    df = pd.read_csv(DATA_PATH, parse_dates=["date"])
    return df.sort_values("date")


def apply_filters(df, args):
    # lọc theo query string, vd /api/rates?year=2024&month=6
    if args.get("start_date"):
        df = df[df["date"] >= pd.to_datetime(args["start_date"])]
    if args.get("end_date"):
        df = df[df["date"] <= pd.to_datetime(args["end_date"])]
    if args.get("year"):
        df = df[df["year"] == int(args["year"])]
    if args.get("month"):
        df = df[df["month"] == int(args["month"])]
    return df


@app.route("/")
def home():
    return "CAD-VND Exchange Rate API"


@app.route("/api/rates")
def get_rates():
    # trả về toàn bộ tỉ giá, có thể lọc theo ngày/tháng/năm
    try:
        df = apply_filters(load_data(), request.args)
        df = df.copy()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        return jsonify(df.to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/rates/date/<date_str>")
def get_rate_by_date(date_str):
    # tra tỉ giá của đúng 1 ngày, vd /api/rates/date/2024-06-03
    try:
        df = load_data()
        row = df[df["date"] == pd.to_datetime(date_str)]
        if row.empty:
            return jsonify({"error": f"No data for {date_str}"}), 404
        row = row.copy()
        row["date"] = row["date"].dt.strftime("%Y-%m-%d")
        return jsonify(row.iloc[0].to_dict())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/overview")
def get_overview():
    # thống kê nhanh: mới nhất, thấp nhất, cao nhất, trung bình
    try:
        df = apply_filters(load_data(), request.args)
        if df.empty:
            return jsonify({"error": "No data in range"}), 404
        latest = df.iloc[-1]
        return jsonify({
            "total_records": len(df),
            "date_range": {"from": df["date"].min().strftime("%Y-%m-%d"),
                            "to": df["date"].max().strftime("%Y-%m-%d")},
            "latest": {"date": latest["date"].strftime("%Y-%m-%d"),
                       "vnd_per_cad": latest["vnd_per_cad"]},
            "min_vnd_per_cad": df["vnd_per_cad"].min(),
            "max_vnd_per_cad": df["vnd_per_cad"].max(),
            "avg_vnd_per_cad": round(df["vnd_per_cad"].mean(), 2),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/timeseries")
def get_timeseries():
    # chuỗi ngày + tỉ giá để vẽ line chart bên client
    try:
        df = apply_filters(load_data(), request.args)
        df = df.copy()
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")
        return jsonify(df[["date", "vnd_per_cad"]].to_dict(orient="records"))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/compare")
def get_compare():
    # trung bình tỉ giá nhóm theo năm và theo tháng
    try:
        df = apply_filters(load_data(), request.args)
        by_year = df.groupby("year")["vnd_per_cad"].mean().round(2).to_dict()
        by_month = df.groupby("month")["vnd_per_cad"].mean().round(2).to_dict()
        return jsonify({"avg_by_year": by_year, "avg_by_month": by_month})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/volatility")
def get_volatility():
    # dùng luôn cột change_pct có sẵn trong data gốc thay vì tự tính lại
    try:
        df = apply_filters(load_data(), request.args)
        if df.empty:
            return jsonify({"error": "Not enough data points"}), 404
        biggest_gain = df.loc[df["change_pct"].idxmax()]
        biggest_drop = df.loc[df["change_pct"].idxmin()]
        return jsonify({
            "series": [{"date": d.strftime("%Y-%m-%d"), "pct_change": p}
                       for d, p in zip(df["date"], df["change_pct"])],
            "biggest_gain": {"date": biggest_gain["date"].strftime("%Y-%m-%d"),
                              "pct_change": round(biggest_gain["change_pct"], 2)},
            "biggest_drop": {"date": biggest_drop["date"].strftime("%Y-%m-%d"),
                              "pct_change": round(biggest_drop["change_pct"], 2)},
            "avg_daily_volatility": round(df["change_pct"].abs().mean(), 3),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/convert")
def convert():
    # quy đổi CAD <-> VND theo tỉ giá mới nhất, hoặc theo ngày cụ thể nếu có ?date=
    try:
        amount = float(request.args.get("amount", 1))
        direction = request.args.get("from", "CAD").upper()  # CAD hoặc VND
        date_str = request.args.get("date")

        df = load_data()
        row = df[df["date"] == pd.to_datetime(date_str)] if date_str else df.tail(1)
        if row.empty:
            return jsonify({"error": f"No rate available for {date_str}"}), 404
        rate = row.iloc[0]
        vnd_per_cad = rate["vnd_per_cad"]

        if direction == "CAD":
            result = round(amount * vnd_per_cad, 2)
            converted_to = "VND"
        elif direction == "VND":
            result = round(amount / vnd_per_cad, 4)
            converted_to = "CAD"
        else:
            return jsonify({"error": "from must be CAD or VND"}), 400

        return jsonify({
            "date_used": rate["date"].strftime("%Y-%m-%d"),
            "rate_vnd_per_cad": vnd_per_cad,
            "input": {"amount": amount, "currency": direction},
            "output": {"amount": result, "currency": converted_to},
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=8080)
