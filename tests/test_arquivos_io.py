"""Arquivos do PC (ler, criar, editar, mover, apagar), blocos de notas, o PC por dentro e envio ao celular."""
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

import pytest

from ametista import acoes, arquivos_io, config, envio, eventos, ferramentas, memoria, notas, sistema
from ametista.identidade import DONO_PADRAO, Falante, falante_atual


@pytest.fixture
def abertos(monkeypatch):
    """Notas que seriam abertas no Bloco de Notas."""
    lista: list[Path] = []
    monkeypatch.setattr(notas, "abrir_no_bloco", lista.append)
    return lista


@pytest.fixture
def casa(tmp_path, monkeypatch, abertos):
    """Uma pasta pessoal de mentira: Documentos, Downloads e Área de Trabalho."""
    home = tmp_path / "casa"
    for p in ("Documents", "Downloads", "Desktop"):
        (home / p).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(arquivos_io, "_pasta_conhecida", lambda guid: None)
    return home


def confirmar():
    assert acoes.pendente() is not None
    tratado, resposta = acoes.resolver_pendente("sim, pode", DONO_PADRAO)
    assert tratado
    return resposta


# ---------------------------------------------------------------- caminhos e segurança
def test_resolver_apelidos_e_nome_solto(casa):
    docs = casa / "Documents"
    assert arquivos_io.resolver("Documentos/estudos/resumo.txt") == docs / "estudos" / "resumo.txt"
    assert arquivos_io.resolver("área de trabalho") == casa / "Desktop"
    assert arquivos_io.resolver("downloads\\x.pdf") == casa / "Downloads" / "x.pdf"
    assert arquivos_io.resolver("~/Downloads/y") == casa / "Downloads" / "y"
    assert arquivos_io.resolver("lista.txt", para_criar=True) == docs / "Ametista" / "lista.txt"
    with pytest.raises(ValueError):
        arquivos_io.resolver("  ")


def test_pasta_das_notas_nao_se_mistura_com_a_instalacao(casa, monkeypatch):
    monkeypatch.setattr(config, "RAIZ", casa / "Documents" / "Ametista")
    assert arquivos_io.pasta_ametista() == casa / "Documents" / "Ametista - arquivos"


def test_pastas_protegidas(casa):
    assert arquivos_io.protegido(config.RAIZ / "ametista" / "config.py")
    assert arquivos_io.protegido(Path(Path.cwd().anchor))
    assert not arquivos_io.protegido(casa / "Documents" / "x.txt")
    if sys.platform == "win32":
        assert arquivos_io.protegido(Path(os.environ["SystemRoot"]) / "System32" / "drivers" / "etc" / "hosts")
        assert arquivos_io.protegido(Path(r"C:\Users"))
    token = falante_atual.set(DONO_PADRAO)
    try:
        r = ferramentas.executar("arquivo_escrever", {"caminho": str(config.RAIZ / "novo.txt"), "conteudo": "x"})
        assert r.startswith("NEGADO") and not (config.RAIZ / "novo.txt").exists()
        r = ferramentas.executar("arquivo_apagar", {"caminho": str(config.RAIZ / "LEIA-ME.md")})
        if acoes.pendente():
            r = confirmar()
        assert "NEGADO" in r and (config.RAIZ / "LEIA-ME.md").exists()
    finally:
        falante_atual.reset(token)


# ---------------------------------------------------------------- leitura
def _docx(p: Path, paragrafos: list[str]) -> None:
    corpo = "".join(f"<w:p><w:r><w:t>{t}</w:t></w:r></w:p>" for t in paragrafos)
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="x"><w:body>{corpo}</w:body></w:document>')


def _xlsx(p: Path) -> None:
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook><sheets><sheet name="Notas" sheetId="1"/></sheets></workbook>')
        z.writestr("xl/sharedStrings.xml", "<sst><si><t>Matéria</t></si><si><t>Cálculo</t></si></sst>")
        z.writestr("xl/worksheets/sheet1.xml",
                   '<worksheet><sheetData><row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="inlineStr">'
                   '<is><t>Nota</t></is></c></row><row r="2"><c r="A2" t="s"><v>1</v></c><c r="B2"><v>9.5</v></c>'
                   '</row></sheetData></worksheet>')


def _pptx(p: Path) -> None:
    with zipfile.ZipFile(p, "w") as z:
        for i, t in ((1, "Introdução"), (2, "Derivadas &amp; limites"), (10, "Fim")):
            z.writestr(f"ppt/slides/slide{i}.xml", f"<p:sld><a:t>{t}</a:t></p:sld>")


def _pdf(p: Path, texto: str) -> None:
    conteudo = f"BT /F1 18 Tf 72 720 Td ({texto}) Tj ET".encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    saida, posicoes = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        posicoes.append(len(saida))
        saida += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(saida)
    saida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    saida += b"".join(b"%010d 00000 n \n" % x for x in posicoes)
    saida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    p.write_bytes(saida)


def test_ler_varios_formatos(casa, dono):
    docs = casa / "Documents"
    (docs / "a.txt").write_text("olá mundo", encoding="utf-8")
    (docs / "antigo.txt").write_bytes("ação em cp1252".encode("cp1252"))
    _docx(docs / "trabalho.docx", ["Título", "Segundo parágrafo"])
    _xlsx(docs / "notas.xlsx")
    _pptx(docs / "aula.pptx")
    _pdf(docs / "apostila.pdf", "Derivadas e integrais")
    (docs / "bin.dat").write_bytes(b"\x00\x01" * 3000)
    assert ferramentas.executar("arquivo_ler", {"caminho": "Documentos/a.txt"}).endswith("):\nolá mundo")
    assert "ação em cp1252" in arquivos_io.ler("Documentos/antigo.txt")
    assert "Título\nSegundo parágrafo" in arquivos_io.ler("Documentos/trabalho.docx")
    assert "--- planilha Notas\nMatéria | Nota\nCálculo | 9.5" in arquivos_io.ler("Documentos/notas.xlsx")
    pptx = arquivos_io.ler("Documentos/aula.pptx")
    assert pptx.index("Introdução") < pptx.index("Derivadas & limites") < pptx.index("Fim")
    assert "Derivadas e integrais" in arquivos_io.ler("Documentos/apostila.pdf")
    assert "não é um arquivo de texto" in arquivos_io.ler("Documentos/bin.dat")
    assert "Não achei" in arquivos_io.ler("Documentos/nada.txt")
    assert acoes.listar(1)[0]["descricao"].startswith("Leu o arquivo")


def test_texto_longo_vem_em_partes(casa):
    (casa / "Documents" / "longo.txt").write_text("a" * 30_000, encoding="utf-8")
    r = arquivos_io.ler("Documentos/longo.txt")
    assert "use inicio=12000" in r and r.count("a") >= 12_000
    r2 = arquivos_io.ler("Documentos/longo.txt", inicio=24_000)
    assert "trecho 24000-30000" in r2 and "use inicio" not in r2


def test_imagem_vem_como_imagem(casa):
    from PIL import Image

    Image.new("RGB", (3000, 2000), "purple").save(casa / "Documents" / "foto.png")
    r = arquivos_io.ler("Documentos/foto.png")
    assert isinstance(r, dict) and r["imagem_b64"] and "foto.png" in r["texto"]


def test_listar_pasta(casa):
    d = casa / "Downloads"
    (d / "sub").mkdir()
    (d / "grande.zip").write_bytes(b"x" * 3_000_000)
    (d / "pequeno.txt").write_text("x")
    (d / "desktop.ini").write_text("x")
    r = arquivos_io.listar("Downloads", ordenar="tamanho")
    assert r.splitlines()[0].endswith("1 pastas e 2 arquivos.")
    assert r.index("[pasta] sub") < r.index("grande.zip  2,9 MB") < r.index("pequeno.txt")
    assert "desktop.ini" not in r


# ---------------------------------------------------------------- escrita, confirmação e desfazer
def test_criar_nao_pede_confirmacao_e_desfaz(casa, dono):
    r = ferramentas.executar("arquivo_escrever", {"caminho": "Documentos/estudos/plano", "conteudo": "1. ler"})
    p = casa / "Documents" / "estudos" / "plano.txt"
    assert r.startswith("Criei") and p.read_text(encoding="utf-8") == "1. ler"
    r = ferramentas.executar("arquivo_escrever", {"caminho": "Documentos/estudos/plano.txt", "conteudo": "2"})
    assert (casa / "Documents" / "estudos" / "plano (2).txt").exists()        # criar nunca sobrescreve
    item = acoes.listar(1)[0]
    assert item["desfazivel"] and acoes.desfazer(item["id"]).startswith("Apaguei plano (2).txt")
    assert not (casa / "Documents" / "estudos" / "plano (2).txt").exists()


def test_mudar_arquivo_existente_pede_confirmacao_e_guarda_copia(casa, dono):
    p = casa / "Desktop" / "lista.txt"
    p.write_text("pão\nleite\n", encoding="utf-8")
    r = ferramentas.executar("arquivo_escrever", {"caminho": str(p), "modo": "trocar", "procurar": "leite",
                                                  "trocar_por": "café"})
    assert r.startswith("PRECISA CONFIRMAR") and "trocar um trecho de lista.txt" in r
    assert p.read_text(encoding="utf-8") == "pão\nleite\n"
    assert confirmar().startswith("Troquei o trecho")
    assert p.read_text(encoding="utf-8") == "pão\ncafé\n"
    item = acoes.listar(1)[0]
    assert item["descricao"] == "Editou o arquivo lista.txt"
    assert acoes.desfazer(item["id"]) == "lista.txt voltou a ser como era."
    assert p.read_text(encoding="utf-8") == "pão\nleite\n"
    # acrescentar e trecho inexistente
    ferramentas.executar("arquivo_escrever", {"caminho": str(p), "modo": "acrescentar", "conteudo": "ovos"})
    confirmar()
    assert p.read_text(encoding="utf-8") == "pão\nleite\novos"
    ferramentas.executar("arquivo_escrever", {"caminho": str(p), "modo": "trocar", "procurar": "xyz"})
    assert "Não encontrei esse trecho" in confirmar()


def test_edicao_mantem_quebras_de_linha_e_codificacao(casa, dono):
    windows = casa / "Desktop" / "windows.txt"
    windows.write_bytes("linha um\r\nlinha dois\r\n".encode("utf-8"))
    ferramentas.executar("arquivo_escrever", {"caminho": str(windows), "modo": "trocar", "procurar": "dois",
                                              "trocar_por": "2\nlinha 3"})
    confirmar()
    assert windows.read_bytes() == "linha um\r\nlinha 2\r\nlinha 3\r\n".encode("utf-8")
    ferramentas.executar("arquivo_escrever", {"caminho": str(windows), "modo": "acrescentar", "conteudo": "fim\n"})
    confirmar()
    assert windows.read_bytes().endswith(b"linha 3\r\nfim\r\n")
    antigo = casa / "Desktop" / "antigo.txt"
    antigo.write_bytes("ação\n".encode("cp1252"))
    ferramentas.executar("arquivo_escrever", {"caminho": str(antigo), "modo": "acrescentar", "conteudo": "coração"})
    confirmar()
    assert antigo.read_bytes() == "ação\ncoração".encode("cp1252")
    ferramentas.executar("arquivo_escrever", {"caminho": str(antigo), "modo": "acrescentar", "conteudo": " ✓"})
    confirmar()
    assert antigo.read_bytes().decode("utf-8") == "ação\ncoração\n ✓"               # ✓ não cabe no cp1252
    novo = casa / "Desktop" / "novo.txt"
    ferramentas.executar("arquivo_escrever", {"caminho": str(novo), "conteudo": "a\nb"})
    assert novo.read_bytes() == (b"a\r\nb" if sys.platform == "win32" else b"a\nb")


def test_nao_escreve_formatos_binarios(casa, dono):
    r = ferramentas.executar("arquivo_escrever", {"caminho": "Documentos/x.docx", "conteudo": "oi"})
    assert r.startswith("Não consigo escrever arquivos .docx")


def test_mover_copiar_e_desfazer(casa, dono):
    origem = casa / "Downloads" / "aula.pdf"
    origem.write_bytes(b"%PDF aula")
    r = ferramentas.executar("arquivo_mover", {"origem": str(origem), "destino": "Documentos/Faculdade"})
    destino = casa / "Documents" / "Faculdade" / "aula.pdf"
    assert r.startswith("Movi aula.pdf") and destino.exists() and not origem.exists()
    assert acoes.desfazer(acoes.listar(1)[0]["id"]) == f"aula.pdf voltou para {origem.parent}."
    assert origem.exists() and not destino.exists()
    # renomear
    ferramentas.executar("arquivo_mover", {"origem": str(origem), "destino": str(casa / "Downloads" / "Aula 1.pdf")})
    assert (casa / "Downloads" / "Aula 1.pdf").exists()
    # copiar por cima de outro pede confirmação e o desfazer devolve o antigo
    alvo = casa / "Desktop" / "Aula 1.pdf"
    alvo.write_bytes(b"antigo")
    r = ferramentas.executar("arquivo_copiar", {"origem": str(casa / "Downloads" / "Aula 1.pdf"),
                                                "destino": "Área de Trabalho"})
    assert r.startswith("PRECISA CONFIRMAR")
    confirmar()
    assert alvo.read_bytes() == b"%PDF aula"
    acoes.desfazer(acoes.listar(1)[0]["id"])
    assert alvo.read_bytes() == b"antigo"


def test_apagar_manda_para_a_lixeira(casa, dono, monkeypatch):
    p = casa / "Desktop" / "velho.txt"
    p.write_text("x")
    r = ferramentas.executar("arquivo_apagar", {"caminho": str(p)})
    assert r.startswith("PRECISA CONFIRMAR") and "velho.txt para a Lixeira" in r and p.exists()
    assert confirmar().startswith("Mandei velho.txt para a Lixeira")
    assert not p.exists()
    if sys.platform != "win32":
        assert (config.DADOS / "lixeira" / "velho.txt").exists()


def test_familia_nao_mexe_em_arquivos(casa):
    token = falante_atual.set(Falante("Ana", "familia"))
    try:
        nomes = {d["name"] for d in ferramentas.definicoes_permitidas()}
        assert not nomes & {"arquivo_ler", "arquivo_escrever", "arquivo_apagar", "nota_criar", "pc_encerrar",
                            "arquivo_enviar_celular", "limpeza_executar"}
        (casa / "Documents" / "segredo.txt").write_text("x")
        assert "segredo" not in ferramentas.executar("arquivo_ler", {"caminho": "Documentos/segredo.txt"})
    finally:
        falante_atual.reset(token)


# ---------------------------------------------------------------- blocos de notas
def test_notas(casa, dono, abertos):
    r = ferramentas.executar("nota_criar", {"titulo": "Lista de compras", "texto": "arroz"})
    p = casa / "Documents" / "Ametista" / "Notas" / "Lista de compras.txt"
    assert r.startswith("Criei a nota Lista de compras e abri no Bloco de Notas") and abertos == [p]
    ferramentas.executar("nota_acrescentar", {"titulo": "lista de compras", "texto": "feijão"})
    assert acoes.pendente() is None                                  # notas dela não pedem confirmação
    assert p.read_text(encoding="utf-8") == "arroz\nfeijão"
    assert "arroz\nfeijão" in ferramentas.executar("nota_ler", {"titulo": "compras"})
    assert ferramentas.executar("notas_listar", {}).startswith("Lista de compras (")
    acoes.desfazer(acoes.listar(1)[0]["id"])
    assert p.read_text(encoding="utf-8") == "arroz"
    ferramentas.executar("nota_criar", {"titulo": 'a/b:c*?', "texto": ""})
    assert (p.parent / "a b c.txt").exists()
    acoes.desfazer(acoes.listar(1)[0]["id"])
    assert not (p.parent / "a b c.txt").exists()


def test_nota_pelo_celular_nao_abre_na_tela(casa, dono, abertos):
    token = ferramentas.CONTEXTO.set({"origem": "celular"})
    try:
        assert "abri" not in notas.criar("Ideia", "x")
    finally:
        ferramentas.CONTEXTO.reset(token)
    assert abertos == []


def test_exportar_conversa(casa, dono):
    troca = memoria.nova_troca()
    memoria.registrar(troca, "user", "qual a capital da França?", quem="Gabriel", origem="celular")
    memoria.registrar(troca, "assistant", "Paris.")
    r = ferramentas.executar("conversa_exportar", {"periodo": "hoje"})
    assert r.startswith("Criei a nota Conversa de ")
    nota = next((casa / "Documents" / "Ametista" / "Notas").glob("Conversa de *.txt"))
    texto = nota.read_text(encoding="utf-8")
    assert "Gabriel (pelo celular): qual a capital da França?" in texto and "Ametista: Paris." in texto
    assert "Não há conversas guardadas em" in notas.exportar_conversa("01/01/2001")


# ---------------------------------------------------------------- o PC por dentro
def test_processos_e_discos():
    r = sistema.processos(quantidade=5)
    assert r.startswith("Memória: ") and r.count("\n- ") == 5
    assert sistema.discos().startswith("Discos:\n- ")


@pytest.fixture
def programa_de_teste(tmp_path):
    """Um processo com nome próprio que não é filho da Ametista (como um programa aberto pelo usuário)."""
    if sys.platform == "win32":
        import psutil

        exe = tmp_path / "ametistateste.exe"
        shutil.copy(sys.executable, exe)
        # pelo "start" do cmd, que sai logo: o programa não fica como filho dos testes (nem da "Ametista")
        subprocess.run(f'cmd /c start "" /b "{exe}" -c "import time; time.sleep(120)"', shell=False)
        pid = 0
        for _ in range(50):
            achados = [p.pid for p in psutil.process_iter(["name"]) if p.info["name"] == "ametistateste.exe"]
            if achados:
                pid = achados[0]
                break
            time.sleep(0.1)
        assert pid, "o programa de teste não abriu"
    else:
        exe = tmp_path / "ametistateste"
        shutil.copy(shutil.which("sleep"), exe)
        pid = int(subprocess.check_output(["sh", "-c", f"'{exe}' 120 >/dev/null 2>&1 & echo $!"]).decode())
    time.sleep(0.5)
    yield pid
    import psutil

    try:
        psutil.Process(pid).kill()
    except psutil.Error:
        pass


def test_encerrar_programa_pede_confirmacao(programa_de_teste, dono):
    import psutil

    r = ferramentas.executar("pc_encerrar", {"programa": "ametistateste"})
    assert r.startswith("PRECISA CONFIRMAR") and "(1 processos," in r
    assert confirmar() == "Fechei o ametistateste (1 processos)."
    time.sleep(0.3)
    assert not psutil.pid_exists(programa_de_teste) or \
        psutil.Process(programa_de_teste).status() == psutil.STATUS_ZOMBIE


def test_nao_encerra_o_windows_nem_a_si_mesma():
    assert sistema.encerrar("svchost").startswith("NEGADO")
    assert sistema.encerrar("explorer.exe").startswith("NEGADO")
    eu = Path(sys.executable).name
    assert "Não achei" in sistema.encerrar(eu) or os.getpid() not in [p.pid for p in sistema._achar(eu)]


def test_limpeza(tmp_path, monkeypatch, dono):
    local = tmp_path / "Local"
    temp = local / "Temp"
    cache = local / "Google" / "Chrome" / "User Data" / "Default" / "Cache" / "Cache_Data"
    for d in (temp / "sub", cache):
        d.mkdir(parents=True)
    velho = time.time() - 3 * 86400
    for arq, tam in ((temp / "a.tmp", 800_000), (temp / "sub" / "b.tmp", 600_000), (cache / "f_0001", 1_500_000)):
        arq.write_bytes(b"x" * tam)
        os.utime(arq, (velho, velho))
    (temp / "novo.tmp").write_bytes(b"x" * 500_000)                   # de hoje: fica
    pessoal = tmp_path / "Documentos"
    pessoal.mkdir()
    (pessoal / "importante.docx").write_bytes(b"x" * 2_000_000)
    os.utime(pessoal / "importante.docx", (velho, velho))
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("TEMP", str(temp))
    monkeypatch.setenv("SystemRoot", str(tmp_path / "Windows"))
    monkeypatch.setattr(sistema, "_lixeira_tamanho", lambda: (0, 0))
    r = sistema.analisar()
    assert r.startswith("Dá para liberar cerca de 3 MB") and "[temporarios]" in r and "[cache_navegadores]" in r
    r = ferramentas.executar("limpeza_executar", {})
    assert r.startswith("PRECISA CONFIRMAR") and "arquivos temporários" in r
    assert confirmar().startswith("Limpei 3 MB (3 arquivos)")
    assert (temp / "novo.tmp").exists() and not (temp / "sub").exists() and (pessoal / "importante.docx").exists()
    # TEMP apontando para um lugar errado: nada é apagado
    monkeypatch.setenv("TEMP", str(pessoal))
    assert not sistema.limpavel(str(pessoal))
    sistema.executar(["temporarios"])
    assert (pessoal / "importante.docx").exists()


# ---------------------------------------------------------------- envio ao celular
class NuvemFalsa:
    def __init__(self, celulares=1):
        self.conectada, self.celulares, self.rele_novo = True, celulares, True
        self.mensagens: list[dict] = []

    def enviar(self, msg):
        self.mensagens.append(msg)
        return True


@pytest.fixture
def nuvem_falsa(monkeypatch):
    from ametista import nuvem

    n = NuvemFalsa()
    monkeypatch.setattr(nuvem, "configurada", lambda: True)
    monkeypatch.setattr(nuvem, "instancia", lambda: n)
    monkeypatch.setattr(envio, "PEDACO", 1000)
    shutil.rmtree(envio.fila_pasta(), ignore_errors=True)
    yield n
    shutil.rmtree(envio.fila_pasta(), ignore_errors=True)


def _esperar_envio(n, partes):
    fim = time.time() + 5
    while time.time() < fim and len(n.mensagens) < partes:
        time.sleep(0.02)


def test_envia_em_pedacos_para_o_celular_que_pediu(casa, dono, nuvem_falsa):
    import base64

    arq = casa / "Documents" / "apostila.pdf"
    dados = os.urandom(2500)
    arq.write_bytes(dados)
    token = ferramentas.CONTEXTO.set({"origem": "celular", "celular": "abc123"})
    try:
        r = ferramentas.executar("arquivo_enviar_celular", {"caminho": "Documentos/apostila.pdf"})
    finally:
        ferramentas.CONTEXTO.reset(token)
    assert r.startswith("Mandando apostila.pdf (2 KB)")
    _esperar_envio(nuvem_falsa, 3)
    msgs = nuvem_falsa.mensagens
    assert [m["parte"] for m in msgs] == [0, 1, 2] and {m["total"] for m in msgs} == {3}
    assert {m["para"] for m in msgs} == {"abc123"} and msgs[0]["mime"] == "application/pdf"
    assert b"".join(base64.b64decode(m["dados"]) for m in msgs) == dados
    assert len(envio.fila()) == 1                                    # só sai quando o celular confirma
    envio.confirmar(msgs[0]["id"])
    assert envio.fila() == []
    assert acoes.listar(1)[0]["descricao"] == "Mandou para o celular: apostila.pdf"


def test_app_fechado_espera_e_entrega_quando_abrir(casa, dono, nuvem_falsa, publicados):
    nuvem_falsa.celulares = 0
    (casa / "Documents" / "Fotos").mkdir()
    (casa / "Documents" / "Fotos" / "a.jpg").write_bytes(b"x" * 100)
    r = envio.enviar("Documentos/Fotos")
    assert "O app do celular está fechado: Fotos.zip ficou esperando" in r
    assert any(e["tipo"] == "notificar_celular" and "Fotos.zip" in e["texto"] for e in publicados)
    assert nuvem_falsa.mensagens == []
    item = envio.fila()[0]
    assert item["temporario"] and zipfile.ZipFile(item["caminho"]).namelist() == ["Fotos/a.jpg"]
    nuvem_falsa.celulares = 1
    assert envio.entregar_fila() == 1
    assert nuvem_falsa.mensagens[0]["nome"] == "Fotos.zip" and "para" not in nuvem_falsa.mensagens[0]
    assert envio.entregar_fila() == 0                                # não repete logo em seguida
    envio.confirmar(item["id"])
    assert not Path(item["caminho"]).exists()                        # o .zip temporário some


def test_limites_do_envio(casa, dono, nuvem_falsa, monkeypatch):
    monkeypatch.setattr(envio, "MAX_BYTES", 1000)
    (casa / "Documents" / "grande.bin").write_bytes(b"x" * 2000)
    assert "passa do limite de 25 MB" in envio.enviar("Documentos/grande.bin")
    assert envio.fila() == []
    assert envio.enviar("Documentos/nao_existe.txt").startswith("Não achei")
    from ametista import nuvem

    monkeypatch.setattr(nuvem, "configurada", lambda: False)
    assert "ainda não foi publicado" in envio.enviar("Documentos/grande.bin")
    assert "arquivo_enviar_celular" not in {d["name"] for d in ferramentas.definicoes_permitidas(DONO_PADRAO)}


def test_nuvem_confirma_o_recebimento(casa, nuvem_falsa):
    from ametista import nuvem

    (casa / "Documents" / "x.txt").write_text("x")
    envio.enviar("Documentos/x.txt")
    _esperar_envio(nuvem_falsa, 1)
    ident = envio.fila()[0]["id"]
    nuvem.Nuvem()._tratar({"tipo": "arquivo_recebido", "arquivo": ident})
    assert envio.fila() == []
