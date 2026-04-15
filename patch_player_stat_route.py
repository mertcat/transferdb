"""
PATCH: Add this route to app.py before the if __name__ == "__main__" block.
It handles per-player stat updates submitted by the referee from submit_result.html.
"""

# ─────────────────────────────────────────────────────────────────────────────
# REFEREE – update individual player stats for a completed match
# ─────────────────────────────────────────────────────────────────────────────

# @app.route("/referee/update_player_stat/<int:match_id>/<int:player_id>", methods=["POST"])
# @role_required("Referee")
# def referee_update_player_stat(match_id, player_id):
#     pid = session["person_id"]
#     db  = get_db()
#     cur = db.cursor(dictionary=True)
#
#     # Verify caller is the assigned referee
#     cur.execute("SELECT referee_id FROM `Match` WHERE match_id = %s", (match_id,))
#     row = cur.fetchone()
#     if not row or row["referee_id"] != pid:
#         flash("You are not the assigned referee for this match.", "danger")
#         cur.close()
#         return redirect(url_for("referee_match_history"))
#
#     minutes  = request.form.get("minutes_played", 90)
#     goals    = request.form.get("goals", 0)
#     assists  = request.form.get("assists", 0)
#     yc       = request.form.get("yellow_cards", 0)
#     rc       = request.form.get("red_cards", 0)
#     rating   = request.form.get("rating", 6.0)
#     position = request.form.get("position_in_match", "TBD").strip()
#
#     try:
#         cur.execute("""
#             UPDATE Lineup
#             SET minutes_played = %s, goals = %s, assists = %s,
#                 yellow_cards = %s, red_cards = %s,
#                 rating = %s, position_in_match = %s
#             WHERE match_id = %s AND player_id = %s
#         """, (minutes, goals, assists, yc, rc, rating, position, match_id, player_id))
#         db.commit()
#         flash("Player stats updated.", "success")
#     except mysql.connector.Error as err:
#         db.rollback()
#         flash(f"Error: {err.msg}", "danger")
#     finally:
#         cur.close()
#
#     return redirect(url_for("referee_submit_result", match_id=match_id))
