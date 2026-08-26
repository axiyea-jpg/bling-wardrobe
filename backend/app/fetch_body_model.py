"""Download the released female local-RFE runtime weights during image build."""

from urllib.request import urlopen

from .settings import settings


BASE = "https://raw.githubusercontent.com/zengyh1900/3D-Human-Body-Shape/master/release_model/"
FILES = {
    "facets.npy": 300080,
    "normals.npy": 150080,
    "female_rfemask.npy": 475080,
    "female_rfemat.npy": 16200080,
    "female_d2v.npz": 14400716,
    "female_mean_measure.npy": 232,
    "female_std_measure.npy": 232,
}


def main() -> None:
    settings.model_dir.mkdir(parents=True, exist_ok=True)
    for name, minimum_size in FILES.items():
        target = settings.model_dir / name
        if target.exists() and target.stat().st_size >= minimum_size:
            continue
        temp = target.with_suffix(target.suffix + ".download")
        with urlopen(BASE + name, timeout=180) as response, temp.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
        if temp.stat().st_size < minimum_size:
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"Incomplete body model file: {name}")
        temp.replace(target)


if __name__ == "__main__":
    main()
