##################################
# config.py
#
# jcarlin@hmc.edu 8 Sept 2025
# SPDX-License-Identifier: Apache-2.0
#
# Parse test framework configuration files
##################################

import shutil
import subprocess
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, DirectoryPath, Field, FilePath, ValidationInfo, field_validator, model_validator
from ruamel.yaml import YAML

from act.toolchain import EXPERIMENTAL_EXTENSIONS, CompilerType, Toolchain

# Boolean parameters of experimental extensions that UDB does not define, with the extension each belongs to
EXPERIMENTAL_PARAMS: dict[str, str] = {
    # Zimt supports 7-bit pointer tags (MT_MODE = 0b11) besides the mandatory 4-bit ones
    "ZIMT_POINTER_TAG_WIDTH_7": "Zimt",
    # The VITT range (protected tag storage) of M-mode, which is implementation-defined, is empty
    "SMVATAG_NO_M_MODE_VITT_RANGE": "Smvatag",
    # The VITT range of a mode with Bare first-stage address translation (satp, or vsatp at V = 1), which is
    # implementation-defined, is empty
    "SVATAG_NO_BARE_VITT_RANGE": "Svatag",
}

# Extensions that an experimental extension depends on, which a config that lists it must implement too
EXPERIMENTAL_REQUIREMENTS: dict[str, frozenset[str]] = {
    # "Svatag depends on Svukte extension and thus assumes an even split in address space between user and supervisor"
    "Svatag": frozenset({"Svukte"}),
}


class RefModelType(str, Enum):
    """Reference model types with their associated flags."""

    SAIL = "sail"

    def signature_flags(self, sig_file: Path | str, granularity: int) -> list[str]:
        """Get the flags for this reference model."""
        flags_map: dict[RefModelType, list[str]] = {
            RefModelType.SAIL: [f"--test-signature={sig_file}", "--signature-granularity", str(granularity)],
        }
        return flags_map[self]


class CoverageSimulator(str, Enum):
    """Coverage simulator backends."""

    QUESTA = "questa"
    VCS = "vcs"
    VERILATOR = "verilator"


class Config(BaseModel):
    """Configuration for the RISC-V architecture verification framework."""

    name: str
    udb_config: FilePath
    linker_script: FilePath
    dut_include_dir: DirectoryPath
    compiler_exe: Path
    objdump_exe: Path | None = None
    compiler_type: CompilerType  # Inferred from compiler_exe by model validator
    ref_model_exe: Path
    ref_model_type: RefModelType  # Inferred from ref_model_exe by model validator
    include_priv_tests: bool = True
    harts: int = Field(default=1, ge=1)
    # Experimental extensions the DUT implements that UDB does not define, so the UDB config cannot list them
    experimental_extensions: frozenset[str] = frozenset()
    # Parameters of those extensions (EXPERIMENTAL_PARAMS), which UDB does not define either
    experimental_params: dict[str, bool] = Field(default_factory=dict)

    model_config = {"frozen": True}

    @property
    def enables_experimental_extensions(self) -> bool:
        """Whether every build of this config enables experimental extensions.

        An experimental extension can change how other extensions' instructions behave (Zimt changes Zimop),
        so the reference model must model it in every test of a DUT that implements it.
        """
        return bool(self.experimental_extensions)

    @property
    def experimental_defines(self) -> tuple[str, ...]:
        """Macros for the experimental extensions and parameters, named as UDB names its extensions and parameters.

        Each extension defines NAME_SUPPORTED and each true parameter defines UDB_NAME, as in rvtest_config.h.
        """
        names = [f"{extension.upper()}_SUPPORTED" for extension in sorted(self.experimental_extensions)]
        names += [f"UDB_{name}" for name, value in sorted(self.experimental_params.items()) if value]
        return tuple(names)

    @field_validator("experimental_extensions")
    @classmethod
    def validate_experimental_extensions(cls, v: frozenset[str]) -> frozenset[str]:
        """Ensure each listed extension is one the framework treats as experimental."""
        unknown = sorted(v - EXPERIMENTAL_EXTENSIONS)
        if unknown:
            raise ValueError(
                f"experimental_extensions lists {', '.join(unknown)}, which are not experimental extensions "
                f"({', '.join(sorted(EXPERIMENTAL_EXTENSIONS))})"
            )
        return v

    @model_validator(mode="after")
    def validate_experimental_params(self) -> "Config":
        """Ensure each parameter is known and belongs to an extension listed in experimental_extensions."""
        for name in sorted(self.experimental_params):
            extension = EXPERIMENTAL_PARAMS.get(name)
            if extension is None:
                raise ValueError(
                    f"experimental_params lists {name}, which is not an experimental parameter "
                    f"({', '.join(sorted(EXPERIMENTAL_PARAMS))})"
                )
            if extension not in self.experimental_extensions:
                raise ValueError(
                    f"experimental_params lists {name}, but experimental_extensions does not list {extension}"
                )
        return self

    @field_validator("compiler_exe", "ref_model_exe", "objdump_exe")
    @classmethod
    def validate_executable(cls, v: Path | None, info: ValidationInfo) -> Path | None:
        """Ensure the executable can be found."""
        if info.context is not None and not info.context.get("validate_tools", True):
            return v
        if v is not None:
            full_path = shutil.which(v)
            if full_path is None:
                raise FileNotFoundError(f"{info.field_name} executable not found: {v}")
            return Path(full_path)
        else:
            return v

    @model_validator(mode="before")
    @classmethod
    def infer_compiler_type(cls, data: dict[str, object]) -> dict[str, object]:
        """Infer compiler type from compiler_exe if not explicitly set."""
        if data.get("compiler_type") is None:
            compiler_exe = data.get("compiler_exe")
            compiler_str = str(compiler_exe) if isinstance(compiler_exe, (str, Path)) else None
            if compiler_str is None:
                raise ValueError("Unable to infer compiler type from compiler_exe.")
            if "clang" in compiler_str:
                data["compiler_type"] = CompilerType.CLANG
            else:
                data["compiler_type"] = CompilerType.GCC
        return data

    @model_validator(mode="before")
    @classmethod
    def infer_ref_model_type(cls, data: dict[str, object]) -> dict[str, object]:
        """Infer reference model type from ref_model_exe if not explicitly set."""
        if data.get("ref_model_type") is None:
            ref_model_exe = data.get("ref_model_exe")
            ref_model_str = str(ref_model_exe) if isinstance(ref_model_exe, (str, Path)) else None
            if ref_model_str is None:
                raise ValueError("Unable to infer reference model type from ref_model_exe.")
            executable_name = Path(ref_model_str).name.lower()
            if "sail" in executable_name:
                data["ref_model_type"] = RefModelType.SAIL
            else:
                raise ValueError(f"Unable to infer reference model type from ref_model_exe: {ref_model_exe}")
        return data

    @field_validator("udb_config", "linker_script", "dut_include_dir", mode="before")
    @classmethod
    def resolve_relative_paths(cls, v: str | None, info: ValidationInfo) -> Path | None:
        """Resolve relative paths relative to config file."""
        if v is None:
            return v
        path = Path(v)
        if path.is_absolute():
            return path
        context = info.context
        if context is None:
            raise ValueError("Unable to resolve relative paths.")
        config_file_dir: Path = context["config_file_dir"]
        return config_file_dir.absolute() / path

    def __str__(self) -> str:
        """Pretty print configuration."""
        lines = ["Configuration:"]
        for field_name, field_value in self.model_dump().items():
            lines.append(f"  {field_name}: {field_value}")
        return "\n".join(lines)


# Minimum required tool versions
REQUIRED_SAIL_VERSION = "0.16"
REQUIRED_GCC_MAJOR_VERSION = 15
REQUIRED_CLANG_MAJOR_VERSION = 20


def check_ref_model_version(config: Config) -> None:
    """Check that the reference model version is compatible."""
    if config.ref_model_type == RefModelType.SAIL:
        try:
            result = subprocess.run(
                [str(config.ref_model_exe), "--version"],
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            version = result.stdout.strip()
            if version != REQUIRED_SAIL_VERSION:
                raise ValueError(
                    f"Sail reference model version mismatch. ACT4 requires version {REQUIRED_SAIL_VERSION}, but {version} was found. "
                    "Refer to the ACT4 README for installation instructions: https://github.com/riscv/riscv-arch-test/tree/act4?tab=readme-ov-file#4-risc-v-sail-reference-model",
                )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"Failed to check Sail version: {e}") from e
        except subprocess.TimeoutExpired as e:
            raise RuntimeError(f"Timeout while checking Sail version: {e}") from e


def check_compiler_version(config: Config) -> None:
    """Check that the compiler is a new enough version."""
    toolchain = Toolchain(config.compiler_exe, config.compiler_type)
    version_str = toolchain.version()
    major_version = int(version_str.split(".")[0])

    if config.compiler_type == CompilerType.GCC:
        required_major = REQUIRED_GCC_MAJOR_VERSION
        compiler_name = "GCC"
    else:
        required_major = REQUIRED_CLANG_MAJOR_VERSION
        compiler_name = "Clang"

    if major_version < required_major:
        raise ValueError(
            f"Compiler version mismatch. ACT4 requires {compiler_name} {required_major} or later, but {version_str} was found. "
            "Refer to the ACT4 README for details: https://github.com/riscv/riscv-arch-test/tree/act4?tab=readme-ov-file#3-risc-v-compiler",
        )


def check_experimental_requirements(config: Config, implemented_extensions: frozenset[str]) -> None:
    """Ensure a config implements the extensions that its experimental extensions depend on.

    implemented_extensions holds the extensions of its UDB config and its experimental extensions.
    """
    for extension in sorted(config.experimental_extensions):
        missing = sorted(EXPERIMENTAL_REQUIREMENTS.get(extension, frozenset()) - implemented_extensions)
        if missing:
            raise ValueError(
                f"{config.name}: experimental_extensions lists {extension}, which depends on {', '.join(missing)}, "
                "but the configuration does not implement it"
            )


def load_config(config_file: Path, *, validate_tools: bool = True) -> Config:
    """Load riscv-arch-test framework configuration from a YAML file."""
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_file}")

    yaml = YAML(typ="safe", pure=True)
    with config_file.open() as f:
        yaml_data = yaml.load(f)

    if yaml_data is None:
        raise ValueError(f"Configuration file is empty: {config_file}")

    config = Config.model_validate(
        yaml_data, context={"config_file_dir": config_file.parent, "validate_tools": validate_tools}
    )
    if validate_tools:
        check_ref_model_version(config)
        check_compiler_version(config)
    return config
