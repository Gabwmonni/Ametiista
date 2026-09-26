"""Objetos falsos para testar sem internet: um "Claude" que responde o que o teste mandar."""
from types import SimpleNamespace


def texto(t: str):
    return SimpleNamespace(type="text", text=t)


def ferramenta(nome: str, entrada: dict, id_: str = "toolu_1", toolset: str | None = None):
    b = SimpleNamespace(type="tool_use", id=id_, name=nome, input=entrada)
    if toolset:
        b.toolset_name = toolset
    return b


class Resposta:
    """Uma rodada do Claude: pedaços de texto (streaming) + blocos finais + motivo de parada."""

    def __init__(self, pedacos=(), blocos=None, parada="end_turn"):
        self.pedacos = list(pedacos)
        self.blocos = blocos if blocos is not None else ([texto("".join(self.pedacos))] if self.pedacos else [])
        self.parada = parada


class _Stream:
    def __init__(self, r: Resposta, cliente):
        self.r, self.cliente = r, cliente

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for b in self.r.blocos:
            if b.type in ("tool_use", "server_tool_use"):
                yield SimpleNamespace(type="content_block_start", content_block=b)
        for p in self.r.pedacos:
            if self.cliente.ao_emitir:
                self.cliente.ao_emitir(p)
            yield SimpleNamespace(type="text", text=p)

    def get_final_message(self):
        return SimpleNamespace(content=self.r.blocos, stop_reason=self.r.parada)


class _Mensagens:
    def __init__(self, cliente, beta=False):
        self.cliente, self.beta = cliente, beta

    def stream(self, **params):
        # guarda uma cópia: o código real continua acrescentando mensagens na mesma lista
        self.cliente.chamadas.append({"beta": self.beta, **params, "messages": list(params.get("messages", []))})
        if self.cliente.erro_na_chamada:
            erro = self.cliente.erro_na_chamada.pop(0)
            if erro:
                raise erro
        if not self.cliente.roteiro:
            raise AssertionError("o Claude falso ficou sem respostas no roteiro")
        return _Stream(self.cliente.roteiro.pop(0), self.cliente)


class ClienteFalso:
    def __init__(self, *respostas: Resposta):
        self.roteiro = list(respostas)
        self.chamadas: list[dict] = []
        self.erro_na_chamada: list = []
        self.ao_emitir = None
        self.messages = _Mensagens(self)
        self.beta = SimpleNamespace(messages=_Mensagens(self, beta=True))


class SaidaFalsa:
    """Substitui o Locutor: guarda o texto e as emoções recebidas."""

    def __init__(self):
        self.pedacos: list[str] = []
        self.emocoes: list[str] = []

    def texto(self, t):
        self.pedacos.append(t)

    def emocao(self, e):
        self.emocoes.append(e)

    @property
    def tudo(self) -> str:
        return "".join(self.pedacos)
