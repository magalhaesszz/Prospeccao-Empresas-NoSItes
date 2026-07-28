{ pkgs }: {
  deps = [
    pkgs.chromium
    pkgs.chromedriver
    pkgs.python311
    pkgs.python311Packages.pip
    pkgs.gcc
    pkgs.zlib
  ];
}
