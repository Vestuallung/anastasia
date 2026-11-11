import Cocoa
import WebKit
import Darwin

@main
struct DesktopMain {
    static func main() {
        let app = NSApplication.shared
        let delegate = DesktopDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.regular)
        withExtendedLifetime(delegate) { app.run() }
    }
}

final class DesktopDelegate: NSObject, NSApplicationDelegate, WKScriptMessageHandler, WKNavigationDelegate, WKUIDelegate, WKDownloadDelegate {
    var window: NSWindow!
    var web: WKWebView!
    var backend: Process?
    var outputPipe: Pipe?
    var attempts = 0
    var generation = 0
    var errors = ""
    var currentProject: URL?
    var backendURL: URL?
    var initialProject: URL?
    var lastDirectory: URL?
    var root: URL { Bundle.main.bundleURL.deletingLastPathComponent() }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let menu = NSMenu()
        let appItem = NSMenuItem(); menu.addItem(appItem)
        let appMenu = NSMenu(); appItem.submenu = appMenu
        appMenu.addItem(withTitle: "关于 Karaoke Studio", action: #selector(about), keyEquivalent: "")
        appMenu.addItem(withTitle: "设置…", action: #selector(showSettings), keyEquivalent: ",")
        appMenu.addItem(.separator())
        appMenu.addItem(withTitle: "退出 Karaoke Studio", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        let file = NSMenuItem(); menu.addItem(file); file.submenu = NSMenu(title: "文件"); file.title = "文件"
        file.submenu?.addItem(withTitle: "新建制作…", action: #selector(newProduction), keyEquivalent: "n")
        file.submenu?.addItem(withTitle: "打开项目…", action: #selector(openProject), keyEquivalent: "o")
        let edit = NSMenuItem(); menu.addItem(edit); edit.title = "编辑"; edit.submenu = NSMenu(title: "编辑")
        edit.submenu?.addItem(withTitle: "撤销", action: #selector(undoEditor), keyEquivalent: "z")
        for (title, action, key) in [("剪切", "cut:", "x"), ("复制", "copy:", "c"), ("粘贴", "paste:", "v"), ("全选", "selectAll:", "a")] {
            edit.submenu?.addItem(withTitle: title, action: Selector(action), keyEquivalent: key)
        }
        NSApplication.shared.mainMenu = menu
        let config = WKWebViewConfiguration()
        config.mediaTypesRequiringUserActionForPlayback = []
        config.userContentController.add(self, name: "desktop")
        web = WKWebView(frame: .zero, configuration: config)
        web.navigationDelegate = self
        web.uiDelegate = self
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 1440, height: 1000), styleMask: [.titled, .closable, .miniaturizable, .resizable], backing: .buffered, defer: false)
        window.minSize = NSSize(width: 1024, height: 720)
        window.title = "Karaoke Studio"
        window.contentView = web
        window.center(); window.makeKeyAndOrderFront(nil)
        NSApplication.shared.activate(ignoringOtherApps: true)
        web.loadHTMLString("<body style='background:#f4f5f8;font:14px -apple-system;color:#73788b;display:grid;place-items:center;height:90vh'>打开 Karaoke 项目</body>", baseURL: nil)
        let args = ProcessInfo.processInfo.arguments
        if let index = args.firstIndex(of: "--project"), index + 1 < args.count { initialProject = URL(fileURLWithPath: args[index+1]) }
        let workspace: URL?
        if let index = args.firstIndex(of: "--workspace"), index + 1 < args.count { workspace = URL(fileURLWithPath: args[index+1]) }
        else if let configured = ProcessInfo.processInfo.environment["KARAOKE_WORKSPACE"] { workspace = URL(fileURLWithPath: configured) }
        else { workspace = nil }
        launchWorkspace(workspace)
    }
    @objc func undoEditor() { web.evaluateJavaScript("document.querySelector('[aria-label=\"撤销\"]')?.click()") }
    @objc func showSettings() { web.evaluateJavaScript("document.querySelector('button[aria-label=\"设置\"],button[aria-label=\"应用设置\"]')?.click()") }
    @objc func newProduction() { web.evaluateJavaScript("window.location.assign('/?new=1')") }
    @objc func about() { NSApplication.shared.orderFrontStandardAboutPanel(options: [.applicationName:"Karaoke Studio", .applicationVersion:"0.2.0"]) }
    @objc func openProject() {
        let panel = NSOpenPanel(); panel.canChooseDirectories = true; panel.canChooseFiles = false; panel.allowsMultipleSelection = false
        panel.prompt = "打开"; panel.message = "选择 Karaoke 项目"; panel.directoryURL = currentProject ?? root
        panel.beginSheetModal(for: window) { [weak self] result in
            guard result == .OK, let path = panel.url else { return }; self?.activateProject(path)
        }
    }
    func freePort() throws -> Int {
        let fd = socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { throw NSError(domain: "socket", code: 1) }; defer { close(fd) }
        var address = sockaddr_in(); address.sin_family = sa_family_t(AF_INET); address.sin_addr.s_addr = inet_addr("127.0.0.1"); address.sin_port = 0
        let bound = withUnsafePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size)) } }
        guard bound == 0 else { throw NSError(domain: "bind", code: 1) }
        var size = socklen_t(MemoryLayout<sockaddr_in>.size)
        withUnsafeMutablePointer(to: &address) { $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { _ = getsockname(fd, $0, &size) } }
        return Int(UInt16(bigEndian: address.sin_port))
    }
    func launchWorkspace(_ workspace: URL?) {
        generation += 1; let ticket = generation
        backend?.terminate(); backend = nil; errors = ""; attempts = 0
        window.title = "Karaoke Studio"
        do {
            let port = try freePort()
            let launcher = root.appendingPathComponent("karaoke-local")
            guard FileManager.default.fileExists(atPath: launcher.path) else {
                alert("请把应用留在 Karaoke Studio 发布目录中，与 karaoke-local 放在一起。")
                return
            }
            let task = Process(); task.executableURL = URL(fileURLWithPath: "/bin/sh")
            task.currentDirectoryURL = URL(fileURLWithPath: "/", isDirectory: true)
            task.arguments = [launcher.path, "desktop", "--port", String(port)]
            if let workspace { task.arguments?.append(contentsOf: ["--workspace", workspace.path]) }
            var env = ProcessInfo.processInfo.environment
            env["PATH"] = env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
            task.environment = env
            let pipe = Pipe(); outputPipe = pipe; task.standardOutput = pipe; task.standardError = pipe
            pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
                let data = handle.availableData
                if data.isEmpty { handle.readabilityHandler = nil; return }
                if let text = String(data: data, encoding: .utf8) { DispatchQueue.main.async { self?.errors = String(((self?.errors ?? "") + text).suffix(2500)) } }
            }
            try task.run(); backend = task
            backendURL = URL(string: "http://127.0.0.1:\(port)/")!
            waitUntilReady(backendURL!, ticket: ticket)
        } catch { alert(error.localizedDescription) }
    }
    func waitUntilReady(_ url: URL, ticket: Int) {
        guard ticket == generation else { return }
        attempts += 1
        var request = URLRequest(url: url); request.timeoutInterval = 1
        URLSession.shared.dataTask(with: request) { [weak self] _, response, _ in
            DispatchQueue.main.async {
                guard let self, ticket == self.generation else { return }
                if let response = response as? HTTPURLResponse, response.statusCode == 200 { if let project = self.initialProject { self.initialProject = nil; self.activateProject(project) }
                    else { self.web.load(URLRequest(url: url)) }; return }
                if self.attempts > 300 || self.backend?.isRunning != true {
                    let status = self.backend?.isRunning == false ? self.backend!.terminationStatus : -1
                    self.alert("启动失败（退出码 \(status)）。首次使用请运行同目录的 Start-Studio 启动文件完成安装。\n\(self.errors)"); return
                }
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { self.waitUntilReady(url, ticket: ticket) }
            }
        }.resume()
    }
    func alert(_ text: String) { let a = NSAlert(); a.messageText = "Karaoke Studio"; a.informativeText = text; a.beginSheetModal(for: window) }
    func activateProject(_ project: URL) {
        guard let backendURL else { return }
        var request = URLRequest(url: backendURL.appendingPathComponent("api/workspace/open"))
        request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(withJSONObject: ["path":project.path])
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            DispatchQueue.main.async {
                guard let self else { return }
                guard error == nil, let data, let value = try? JSONSerialization.jsonObject(with: data) as? [String:Any], let route = value["url"] as? String else {
                    self.alert("无法打开项目，请选择制作项目文件夹"); self.web.load(URLRequest(url:backendURL)); return
                }
                self.currentProject = project
                self.web.load(URLRequest(url: URL(string:route,relativeTo:backendURL)!.absoluteURL))
            }
        }.resume()
    }
    func pickFile(_ value: [String:Any]) {
        guard let id = value["id"] as? String, let kind = value["kind"] as? String else { return }
        let panel = NSOpenPanel(); panel.canChooseDirectories = kind == "project"; panel.canChooseFiles = kind != "project"; panel.allowsMultipleSelection = false
        panel.prompt = "选择"; panel.directoryURL = lastDirectory ?? currentProject ?? root
        panel.beginSheetModal(for:window) { [weak self] result in
            guard let self else { return }
            let path = result == .OK ? panel.url?.path : nil
            if let selected = panel.url, result == .OK { self.lastDirectory = selected.deletingLastPathComponent() }
            let value: [String:Any] = ["id":id,"path":path as Any? ?? NSNull()]
            guard let bytes = try? JSONSerialization.data(withJSONObject:value), let json = String(data:bytes,encoding:.utf8) else { return }
            self.web.evaluateJavaScript("window.dispatchEvent(new CustomEvent('studio-file',{detail:\(json)}))")
        }
    }
    func userContentController(_ userContentController: WKUserContentController, didReceive message: WKScriptMessage) {
        if message.body as? String == "open" { openProject() }
        else if let value = message.body as? [String:Any], value["action"] as? String == "pick" { pickFile(value) }
    }
    func webView(_ webView: WKWebView, createWebViewWith configuration: WKWebViewConfiguration,
                 for navigationAction: WKNavigationAction, windowFeatures: WKWindowFeatures) -> WKWebView? {
        if let url = navigationAction.request.url, ["http", "https"].contains(url.scheme ?? "") {
            NSWorkspace.shared.open(url)
        }
        return nil
    }
    func webView(_ webView: WKWebView, decidePolicyFor navigationAction: WKNavigationAction,
                 decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        decisionHandler(navigationAction.shouldPerformDownload ? .download : .allow)
    }
    func webView(_ webView: WKWebView, navigationAction: WKNavigationAction, didBecome download: WKDownload) {
        download.delegate = self
    }
    func download(_ download: WKDownload, decideDestinationUsing response: URLResponse,
                  suggestedFilename: String, completionHandler: @escaping (URL?) -> Void) {
        let panel = NSSavePanel()
        panel.nameFieldStringValue = suggestedFilename
        panel.beginSheetModal(for: window) { result in
            completionHandler(result == .OK ? panel.url : nil)
        }
    }
    func applicationWillTerminate(_ notification: Notification) { backend?.terminate() }
    func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { true }
}
