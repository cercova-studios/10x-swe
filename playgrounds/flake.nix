{
  description = "Pinned tools for the 10x-swe Linux playground";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/fe13242281a67641c0102cdb1087f0ebe586c7df";
  outputs = { self, nixpkgs }:
    let systems = [ "aarch64-linux" "x86_64-linux" ];
    in {
      packages = nixpkgs.lib.genAttrs systems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          daguPlatform = {
            aarch64-linux = { arch = "arm64"; sha256 = "8931188a8d40d314346cb3f36d0b26c615b0b6c490297801e82811d14856556d"; };
            x86_64-linux = { arch = "amd64"; sha256 = "df2b3d7d27c8e9b206e061e0d6b082ca7d3c3bd205d60453577a955e8991998f"; };
          }.${system};
          dagu = pkgs.stdenvNoCC.mkDerivation {
            pname = "dagu";
            version = "2.19.2";
            src = pkgs.fetchurl {
              url = "https://github.com/dagucloud/dagu/releases/download/v2.19.2/dagu_2.19.2_linux_${daguPlatform.arch}.tar.gz";
              inherit (daguPlatform) sha256;
            };
            sourceRoot = ".";
            dontConfigure = true;
            dontBuild = true;
            installPhase = "install -Dm755 dagu $out/bin/dagu";
          };
        in { default = pkgs.buildEnv {
          name = "10x-swe-playground";
          paths = with pkgs; [
            bashInteractive coreutils findutils gnutar gzip git ripgrep jq sqlite
            python312 rustc cargo go gcc pkg-config openssl pandoc
          ] ++ [ dagu ];
          pathsToLink = [ "/bin" "/lib" "/include" "/share" ];
          extraOutputsToInstall = [ "dev" ];
        }; });
    };
}
