# Instagram Downloader (yt-dlp + gallery-dl)

Uma aplicação web local projetada para baixar mídias do Instagram (Vídeos, Carrosséis, Stories, Perfis e Hashtags) contornando os recentes bloqueios e mudanças na API GraphQL do Instagram.

## Arquitetura
Originalmente desenhado para usar o `instaloader`, o motor principal foi substituído por uma combinação robusta do **yt-dlp** (excelente para vídeos) e do **gallery-dl** (excepcional para álbuns de fotos, stories e perfis inteiros). 

Isso garante estabilidade, já que essas duas ferramentas estão sempre atualizadas e são independentes das rotas problemáticas do Graph API.

## Funcionalidades
* **Download Avulso:** Cole o link de qualquer post ou Reel e baixe rapidamente.
* **Perfil Completo:** Baixe tudo de um usuário: Feed (fotos e vídeos), apenas vídeos, ou baixe todos os Stories das últimas 24h.
* **Hashtags:** Explore e baixe todas as imagens e vídeos recentes baseados em uma `#hashtag`.
* **Filtros de Data:** Configure uma data de início ("A partir de") para ignorar posts antigos em perfis muito grandes.
* **Organização de Pastas Dinâmica:** Todo arquivo baixado é automaticamente organizado por `nome_do_autor`.
* **Extração de Metadados:** Salve informações cruciais (Legendas, quantidade de curtidas, tags) junto com a imagem, sem custo de chamadas extras na API, evitando banimentos.

## Como fazer o Login e Evitar o "Erro 403 Forbidden"
O Instagram bloqueia agressivamente conexões não autenticadas. Para acessar conteúdos e não ser bloqueado, você deve "logar" o app. Existem duas formas de fazer isso na aba de Login (botão "Fazer Login" no topo):

1. **Aba "Cookie do Browser" (O mais seguro e recomendado):**
   - Abra o Instagram no seu navegador e logue normalmente.
   - Pressione `F12` para abrir as Ferramentas de Desenvolvedor e vá na aba "Rede" (Network).
   - Recarregue a página (`F5`).
   - Clique em qualquer requisição, vá em "Cabeçalhos" (Headers) -> "Request Headers" e copie **todo o conteúdo** do parâmetro `cookie:`.
   - Cole no aplicativo. Ele converterá tudo para um arquivo Netscape e suas sessões estarão 100% autênticas!

2. **Aba "Login Automático" (Robô):**
   - Ao clicar no botão, o app abrirá uma janela "limpa" do navegador Chromium.
   - Basta você realizar o login no site do Instagram normalmente por lá.
   - Quando você logar com sucesso, a janela se fechará automaticamente, e o robô salvará seus cookies para os próximos downloads. Muito mais prático!

---

## Como Rodar o Projeto

1. Certifique-se de ter o Python 3 instalado.
2. Instale as dependências:
   ```bash
   pip install flask yt-dlp gallery-dl playwright
   ```
3. Instale o navegador interno usado para o login automático:
   ```bash
   python -m playwright install chromium
   ```
4. Inicie o servidor:
   ```bash
   python app.py
   ```
5. Abra no navegador: `http://localhost:5000`
