#!/usr/bin/env python3
"""Unit tests for paginated site list parser (no network)."""

from email_parser.site_list import SiteListParser


def test_extract_external_sites():
    html = """
    <html><body>
      <a href="https://partner-one.ru/about">One</a>
      <a href="https://www.partner-two.com">Two</a>
      <a href="/local/page">Local</a>
      <a href="mailto:a@b.ru">mail</a>
      <a href="https://partner-one.ru/contacts">One again</a>
    </body></html>
    """
    parser = SiteListParser(external_only=True)
    sites = parser.extract_sites(html, "https://catalog.example/list")
    assert sites == ["https://partner-one.ru", "https://www.partner-two.com"]


def test_link_selector():
    html = """
    <div class="card"><a class="site" href="https://a.ru">A</a></div>
    <a href="https://noise.com">noise</a>
    """
    parser = SiteListParser(link_selector="a.site")
    sites = parser.extract_sites(html, "https://catalog.example/")
    assert sites == ["https://a.ru"]


def test_next_rel_and_text():
    parser = SiteListParser()
    html = '<a rel="next" href="/list?page=2">Следующая</a>'
    nxt = parser.find_next_url(html, "https://catalog.example/list?page=1", 1)
    assert nxt == "https://catalog.example/list?page=2"

    html2 = '<a class="pagination-next" href="/page/3/">Дальше</a>'
    nxt2 = parser.find_next_url(html2, "https://catalog.example/page/2/", 2)
    assert nxt2 == "https://catalog.example/page/3/"


def test_page_param():
    parser = SiteListParser(page_param="page")
    nxt = parser.find_next_url("<html></html>", "https://x.test/partners?page=4", 4)
    assert "page=5" in nxt


def test_page_number_inp_1c():
    parser = SiteListParser()
    url = (
        "https://1c.ru/rus/partners/franch-citylist.jsp"
        "?reg=&city=&partnerName=&is_map_open=0&mark=true&pageNumber_inp=2"
    )
    nxt = parser.find_next_url("<html></html>", url, 2)
    assert "pageNumber_inp=3" in nxt


def test_extract_from_js_embedded_html():
    html = r'''
    var balloon = "Сайт: <a href=http://rarus.ru target=\"_blank\">http://rarus.ru</a>";
    <td><a href="http://www.hs.by/" style="color: #333333;" target="blank"><small>http://www.hs.by/</small></a></td>
    <a href="https://buh.ru/">БУХ.1С</a>
    '''
    parser = SiteListParser(external_only=True)
    sites = parser.extract_sites(html, "https://1c.ru/rus/partners/franch-citylist.jsp")
    assert "https://rarus.ru" in sites
    assert "https://www.hs.by" in sites
    assert "https://buh.ru" not in sites  # blocked nav link


def test_path_pagination():
    parser = SiteListParser()
    nxt = parser.find_next_url("<html></html>", "https://x.test/partners/page/7/", 7)
    assert nxt.endswith("/partners/page/8/")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("all passed")
