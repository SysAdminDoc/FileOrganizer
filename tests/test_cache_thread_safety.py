from concurrent.futures import ThreadPoolExecutor

import fileorganizer.cache as cache


def test_classification_cache_is_safe_across_worker_threads(tmp_path, monkeypatch):
    database = tmp_path / "classification-cache.db"
    monkeypatch.setattr(cache, "_CACHE_DB", str(database))
    cache._close_cache_conn()

    folders = []
    for index in range(64):
        folder = tmp_path / f"folder-{index}"
        folder.mkdir()
        (folder / "asset.txt").write_text(str(index), encoding="utf-8")
        folders.append(folder)

    def store(index: int) -> None:
        cache.cache_store(
            folders[index].name,
            folders[index],
            {
                "category": f"category-{index}",
                "confidence": 90,
                "cleaned_name": folders[index].name,
                "method": "test",
            },
        )

    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(store, range(len(folders))))

        assert cache.cache_count() == len(folders)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(
                lambda index: cache.cache_lookup(folders[index].name, folders[index]),
                range(len(folders)),
            ))
        assert [result["category"] for result in results] == [
            f"category-{index}" for index in range(len(folders))
        ]
    finally:
        cache._close_cache_conn()
