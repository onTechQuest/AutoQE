const net = require("node:net");

const allowedHosts = new Set(["localhost", "127.0.0.1", "::1"]);
const originalListen = net.Server.prototype.listen;

function safeHost(host) {
  if (host === undefined || host === null || host === "" || host === "0.0.0.0" || host === "::") {
    return "127.0.0.1";
  }
  if (typeof host === "string" && allowedHosts.has(host.toLowerCase())) {
    return host;
  }
  throw new Error("M3 reference execution refuses non-loopback Node listener: " + String(host));
}

function isDetectPortProbe() {
  return /[\\/]detect-port[\\/]/i.test(new Error().stack || "");
}

net.Server.prototype.listen = function (...args) {
  const probeHost = isDetectPortProbe() ? "127.0.0.1" : null;
  if (typeof args[0] === "number") {
    if (typeof args[1] === "string") {
      args[1] = probeHost || safeHost(args[1]);
    } else {
      args.splice(1, 0, probeHost || safeHost(undefined));
    }
  } else if (args[0] && typeof args[0] === "object" && Object.hasOwn(args[0], "port")) {
    args[0] = { ...args[0], host: probeHost || safeHost(args[0].host) };
  }
  return originalListen.apply(this, args);
};