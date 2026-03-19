"""
Здесь можно организовать бизнес-логику, специфичную для конкретного сервиса.
"""
from langgraph.graph import StateGraph, START, END

from aigw_ct.api.v1.nodes.nodes import NodesHelper
from aigw_ct.api.v1.schemas import Statement
from aigw_ct.context import APP_CTX

ecm_config = APP_CTX.get_ecm_config()
logger = APP_CTX.get_logger()


async def main(state: Statement):
    nodes = NodesHelper()

    graph = StateGraph(Statement)

    graph.add_node("ecm_function", nodes.ecm_retrieve_contents)
    graph.add_node("split_text_forms", nodes.split_text_forms)

    # right nodes
    graph.add_node("markup", nodes.generate_forms_markup)
    graph.add_node("extract_forms", nodes.extract_forms)
    graph.add_node("prepare_fill_forms", nodes.prepare_fill_forms)
    graph.add_node("skip_node", nodes.skip_node)
    graph.add_node("combine_answer", nodes.combine_answer)
    graph.add_node("fill_forms", nodes.fill_forms)
    graph.add_node("save_data_ecm", nodes.save_data_in_ecm)

    # left nodes
    graph.add_node("list_requirements", nodes.list_requirements)
    graph.add_node("reducer_lst_req", nodes.reducer_lst_req)
    graph.add_node("react_agent", nodes.react_agent)

    graph.add_edge(START, "ecm_function")
    graph.add_conditional_edges("ecm_function", nodes.router_after_ecm, {"end": END, "next": "skip_node"})
    graph.add_edge("skip_node", "split_text_forms")

    # right branch
    graph.add_edge("split_text_forms", "markup")
    graph.add_edge("markup", "extract_forms")
    graph.add_conditional_edges("extract_forms", nodes.check_forms, {False: "combine_answer", True: "prepare_fill_forms"})
    graph.add_edge("prepare_fill_forms", "fill_forms")
    graph.add_edge("fill_forms", "save_data_ecm")
    graph.add_edge("save_data_ecm", "combine_answer")

    # left branch
    graph.add_edge("split_text_forms", "list_requirements")
    graph.add_edge("list_requirements", "reducer_lst_req")
    graph.add_edge("reducer_lst_req", "react_agent")
    graph.add_edge("react_agent", "combine_answer")

    graph.add_edge("combine_answer", END)

    app = graph.compile()

    result = await app.ainvoke(state)

    return result