"""Semester groups (SPEC_semester_groups.md D1, D7, D8): where web-push puts a course, old flat copies in grade_web,
and which copy web-pull reads."""
import json
import shutil

from webtools import F1, P1, csv_cell, grader_cli, mirror, old_mirror, put_journal, tree_sha

HW = f"data/{P1}_homework.csv"


def semester_course(tmp_path, web_course, semester="2569-1"):
    """F1 moved under a semester folder on the Mac side: <tmp>/teachings/<semester>/<F1>."""
    dest = tmp_path / "teachings" / semester / F1
    dest.parent.mkdir(parents=True)
    shutil.move(str(web_course), dest)
    return dest


def push(course, *extra):
    return grader_cli(["web-push", str(course), *extra])


def pull(course, *extra):
    return grader_cli(["web-pull", str(course), *extra])


def old_copy(drive_root, course, journal=None):
    """A copy where web-push put it before semester groups (grade_web/<course>), from a push to the new place."""
    code, out = push(course)
    assert code == 0, out
    old = old_mirror(drive_root, course)
    shutil.copytree(mirror(drive_root, course), old)
    shutil.rmtree(mirror(drive_root, course).parent.parent)
    if journal:
        put_journal(old, journal)
    return old


def test_push_goes_to_the_semester_folder_and_hints_the_shortcut(tmp_path, web_course, drive_root):
    c = semester_course(tmp_path, web_course)
    code, out = push(c)
    assert code == 0, out
    target = drive_root / "grade_courses" / "2569-1" / F1
    assert (target / "course.json").is_file() and (target / "web_edits.jsonl").is_file()
    assert f"🔄 Web push: {F1} → My Drive/grade_courses/2569-1/{F1}/" in out
    assert not (drive_root / "grade_web").exists(), "web-push never writes into grade_web"
    assert ("   The phone lists it once grade_web has a shortcut to grade_courses/2569-1: in Drive, right-click "
            "2569-1 › Organise › Add shortcut › grade_web (once per term).") in out.splitlines()


def test_no_hint_once_grade_web_has_the_semester(tmp_path, web_course, drive_root):
    c = semester_course(tmp_path, web_course)
    (drive_root / "grade_web").mkdir()
    (drive_root / "grade_web" / "2569-1").symlink_to(drive_root / "grade_courses" / "2569-1")
    code, out = push(c)
    assert code == 0, out
    assert "Add shortcut" not in out


def test_semester_flag_and_root_name(tmp_path, web_course, drive_root, monkeypatch):
    c = semester_course(tmp_path, web_course)
    code, out = push(c, "--semester", "2569-S")
    assert code == 0, out
    assert (drive_root / "grade_courses" / "2569-S" / F1 / "push.json").is_file()
    monkeypatch.setenv("GRADE_WEB_COURSES", "Teaching")
    code, out = push(c)
    assert code == 0, out
    assert (drive_root / "Teaching" / "2569-1" / F1 / "push.json").is_file()
    code, out = push(c, "--semester", "a/b")
    assert code == 1
    assert "❌ --semester is a single folder name (no /): a/b. Nothing was written." in out


def test_old_copy_with_unpulled_edits_refuses_push(tmp_path, web_course, drive_root):
    c = semester_course(tmp_path, web_course)
    old = old_copy(drive_root, c, "four_lines.jsonl")
    before = tree_sha(drive_root)
    code, out = push(c, "--force")
    assert code == 1, out
    assert f"❌ The old copy My Drive/grade_web/{F1}/ has 4 web edits not pulled yet" in out
    assert "   Bring them in first:  grader web-pull         (preview, then --yes)" in out
    assert tree_sha(drive_root) == before, "nothing written anywhere"
    assert old.is_dir()


def test_old_copy_without_edits_is_left_and_named(tmp_path, web_course, drive_root):
    c = semester_course(tmp_path, web_course)
    old = old_copy(drive_root, c)
    old_files = tree_sha(old)
    code, out = push(c)
    assert code == 0, out
    assert (mirror(drive_root, c) / "push.json").is_file()
    assert tree_sha(old) == old_files, "the old copy is never changed"
    assert (f"   The old copy My Drive/grade_web/{F1}/ is no longer updated: delete it in Drive "
            "(it has no edits waiting).") in out.splitlines()
    assert "Add shortcut" in out


def test_a_shortcut_to_the_course_is_not_an_old_copy(tmp_path, web_course, drive_root):
    c = semester_course(tmp_path, web_course)
    code, out = push(c)
    assert code == 0, out
    (drive_root / "grade_web").mkdir()
    old_mirror(drive_root, c).symlink_to(mirror(drive_root, c))
    put_journal(mirror(drive_root, c), "four_lines.jsonl")
    code, out = push(c, "--force")
    assert code == 0, out
    assert "old copy" not in out and "Add shortcut" not in out
    # Drive for Desktop may show the shortcut as a folder of its own: the same push_id means the same copy
    old_mirror(drive_root, c).unlink()
    shutil.copytree(mirror(drive_root, c), old_mirror(drive_root, c))
    code, out = push(c)
    assert code == 0, out
    assert "old copy" not in out


def test_pull_reads_the_semester_copy(tmp_path, web_course, drive_root):
    c = semester_course(tmp_path, web_course)
    code, out = push(c)
    assert code == 0, out
    put_journal(mirror(drive_root, c), "four_lines.jsonl")
    code, out = pull(c)
    assert code == 0, out
    assert f"🔄 Web pull: My Drive/grade_courses/2569-1/{F1}/ → {F1}" in out


def test_pull_falls_back_to_the_old_copy(tmp_path, web_course, drive_root):
    c = semester_course(tmp_path, web_course)
    old_copy(drive_root, c, "four_lines.jsonl")
    code, out = pull(c)
    assert code == 0, out
    assert f"🔄 Web pull: My Drive/grade_web/{F1}/ → {F1}" in out
    assert "   Journal: 4 edits not pulled" in out


def test_pull_takes_the_copy_with_edits_and_refuses_two(tmp_path, web_course, drive_root):
    c = semester_course(tmp_path, web_course)
    old = old_copy(drive_root, c, "four_lines.jsonl")
    shutil.copytree(old, mirror(drive_root, c))
    (mirror(drive_root, c) / "web_edits.jsonl").write_bytes(b"")
    push_json = json.loads((mirror(drive_root, c) / "push.json").read_text(encoding="utf-8"))
    push_json["push_id"] = "p-20270121-090000"
    (mirror(drive_root, c) / "push.json").write_text(json.dumps(push_json), encoding="utf-8")
    code, out = pull(c, "--yes")
    assert code == 0, out
    assert f"🔄 Web pull: My Drive/grade_web/{F1}/ → {F1}" in out
    put_journal(old, "four_lines.jsonl")
    put_journal(mirror(drive_root, c), "four_lines.jsonl")
    for f in (old, mirror(drive_root, c)):
        shutil.rmtree(f / "archive", ignore_errors=True)
    before = tree_sha(c)
    code, out = pull(c, "--yes")
    assert code == 1, out
    assert (f"❌ Two Drive copies of {F1} have web edits not pulled: My Drive/grade_courses/2569-1/{F1}/ and "
            f"My Drive/grade_web/{F1}/.") in out
    assert tree_sha(c) == before
