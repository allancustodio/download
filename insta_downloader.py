#!/usr/bin/env python3
"""
Instagram Downloader — instaloader
Baixa conteúdo de perfis públicos do Instagram.
"""

import instaloader
import os
import sys

# ──────────────────────────────────────────────
# CONFIGURAÇÕES
# ──────────────────────────────────────────────
OUTPUT_DIR = "downloads"          # Pasta onde os arquivos serão salvos
SLEEP_MIN  = 2                    # Pausa mínima entre downloads (segundos)
SLEEP_MAX  = 6                    # Pausa máxima (evita rate limit do Instagram)


def menu_opcoes() -> int:
    print("\n┌─────────────────────────────────┐")
    print("│   Instagram Downloader          │")
    print("├─────────────────────────────────┤")
    print("│  O que deseja baixar?           │")
    print("│                                 │")
    print("│  1 - Só vídeos do feed          │")
    print("│  2 - Vídeos + Reels             │")
    print("│  3 - Fotos + Vídeos do feed     │")
    print("│  4 - Tudo (feed + reels +       │")
    print("│      stories + destaques)       │")
    print("│  0 - Sair                       │")
    print("└─────────────────────────────────┘")
    while True:
        try:
            opcao = int(input("\nEscolha: "))
            if opcao in [0, 1, 2, 3, 4]:
                return opcao
            print("Opção inválida. Tente novamente.")
        except ValueError:
            print("Digite um número.")


def criar_loader(opcao: int) -> instaloader.Instaloader:
    """Configura o Instaloader de acordo com a opção escolhida."""

    # Defaults — nada baixado
    base = dict(
        download_pictures    = False,
        download_videos      = False,
        download_video_thumbnails = False,
        download_geotags     = False,
        download_comments    = False,
        save_metadata        = False,
        compress_json        = False,
        post_metadata_txt_pattern = "",   # sem .txt extras
        filename_pattern     = "{date_utc:%Y-%m-%d}_{shortcode}",
        sleep               = True,
        quiet               = False,
    )

    if opcao == 1:   # Só vídeos do feed
        base["download_videos"] = True

    elif opcao == 2: # Vídeos + Reels
        base["download_videos"] = True

    elif opcao == 3: # Fotos + Vídeos do feed
        base["download_pictures"] = True
        base["download_videos"]   = True

    elif opcao == 4: # Tudo
        base["download_pictures"] = True
        base["download_videos"]   = True

    return instaloader.Instaloader(**base)


def baixar_stories(L: instaloader.Instaloader, profile: instaloader.Profile):
    """Baixa stories (requer login para perfis que não sejam o seu)."""
    try:
        L.download_stories(userids=[profile.userid])
        print("✔ Stories baixados.")
    except Exception as e:
        print(f"⚠  Não foi possível baixar stories: {e}")


def baixar_destaques(L: instaloader.Instaloader, profile: instaloader.Profile):
    """Baixa highlights/destaques."""
    try:
        for highlight in L.get_highlights(profile):
            L.download_highlight(highlight)
        print("✔ Destaques baixados.")
    except Exception as e:
        print(f"⚠  Não foi possível baixar destaques: {e}")


def baixar_reels(L: instaloader.Instaloader, profile: instaloader.Profile):
    """Filtra e baixa apenas posts do tipo Reel."""
    print("\n⏳ Procurando Reels...")
    count = 0
    for post in profile.get_posts():
        if post.is_video and post.product_type == "clips":  # "clips" = Reel
            L.download_post(post, target=profile.username)
            count += 1
    print(f"✔ {count} Reels baixados.")


def main():
    opcao = menu_opcoes()
    if opcao == 0:
        print("Saindo.")
        sys.exit(0)

    username = input("\nDigite o @ do perfil (sem @): ").strip().lstrip("@")
    if not username:
        print("Username inválido.")
        sys.exit(1)

    # Cria pasta de saída
    pasta_destino = os.path.join(OUTPUT_DIR, username)
    os.makedirs(pasta_destino, exist_ok=True)
    os.chdir(pasta_destino)

    print(f"\n📁 Salvando em: {os.path.abspath('.')}")
    print(f"🔗 Perfil     : @{username}")
    print(f"📥 Opção      : {opcao}\n")

    L = criar_loader(opcao)

    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"❌ Perfil @{username} não encontrado.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro ao acessar perfil: {e}")
        sys.exit(1)

    print(f"✅ Perfil encontrado: {profile.full_name}")
    print(f"   Posts  : {profile.mediacount}")
    print(f"   Seguidores: {profile.followers}\n")

    # ── OPÇÃO 1: Só vídeos do feed ──────────────────
    if opcao == 1:
        print("⏳ Baixando vídeos do feed...")
        for post in profile.get_posts():
            if post.is_video:
                L.download_post(post, target=profile.username)

    # ── OPÇÃO 2: Vídeos + Reels ─────────────────────
    elif opcao == 2:
        print("⏳ Baixando vídeos do feed...")
        for post in profile.get_posts():
            if post.is_video:
                L.download_post(post, target=profile.username)
        baixar_reels(L, profile)

    # ── OPÇÃO 3: Fotos + Vídeos do feed ─────────────
    elif opcao == 3:
        print("⏳ Baixando fotos e vídeos do feed...")
        L.download_profile(profile, tagged=False)

    # ── OPÇÃO 4: Tudo ────────────────────────────────
    elif opcao == 4:
        print("⏳ Baixando feed completo...")
        L.download_profile(profile, tagged=False)
        baixar_reels(L, profile)
        baixar_stories(L, profile)
        baixar_destaques(L, profile)

    print("\n🎉 Download concluído!")
    print(f"📁 Arquivos em: {os.path.abspath('.')}")


if __name__ == "__main__":
    main()