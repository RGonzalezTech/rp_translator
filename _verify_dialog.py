"""Quick smoke test for CharacterDialog — must be run manually (GUI)."""
import sqlite3
import tkinter as tk
from rp_translator import init_db, add_character, add_voice_example, CharacterDialog

root = tk.Tk()
root.withdraw()  # hide root

conn = sqlite3.connect(":memory:")
init_db(conn)

# Add a test character for edit-mode verification
cid = add_character(conn, "Thrall", "Orc", "Shaman",
                    "Warchief of the Horde", "Speaks in proverbs")
add_voice_example(conn, cid, "gj", "Lok'tar ogar!")
add_voice_example(conn, cid, "help", "The elements guide us.")

print("Opening create dialog...")
dlg1 = CharacterDialog(root, conn)
root.wait_window(dlg1)
if dlg1.result:
    print(f"Created: {dlg1.result['name']} (id={dlg1.result['id']})")
    cid = dlg1.result["id"]
else:
    print("Create cancelled, using pre-seeded character for edit test")

print("\nOpening edit dialog...")
dlg2 = CharacterDialog(root, conn, character_id=cid)
root.wait_window(dlg2)
if dlg2.result:
    print(f"Edited: {dlg2.result['name']}")
else:
    print("Edit cancelled")

print("Done.")
root.destroy()
