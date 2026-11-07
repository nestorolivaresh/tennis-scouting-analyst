from ingest.download import git_blob_sha1, sha256, verify

# Expected values come from git itself: `printf 'hello\n' | git hash-object --stdin`
# and `printf '' | git hash-object --stdin` (git 2.45.2).
GIT_HASH_HELLO = "ce013625030ba8dba906f756967f9e9ca394464a"
GIT_HASH_EMPTY = "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"


def test_git_blob_sha1_matches_git_hash_object():
    assert git_blob_sha1(b"hello\n") == GIT_HASH_HELLO
    assert git_blob_sha1(b"") == GIT_HASH_EMPTY


def test_verify_accepts_matching_bytes():
    data = b"hello\n"
    entry = {"sha256": sha256(data), "git_blob_sha1": GIT_HASH_HELLO}
    assert verify(data, entry) is None


def test_verify_rejects_changed_bytes():
    entry = {"sha256": sha256(b"hello\n"), "git_blob_sha1": GIT_HASH_HELLO}
    assert "sha256" in verify(b"hello!\n", entry)


def test_verify_checks_git_blob_hash_when_present():
    data = b"hello\n"
    entry = {"sha256": sha256(data), "git_blob_sha1": GIT_HASH_EMPTY}
    assert "git blob" in verify(data, entry)
