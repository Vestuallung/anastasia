import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => cleanup());

vi.stubGlobal("PointerEvent", MouseEvent);

Object.defineProperty(HTMLMediaElement.prototype, "play", {
  configurable: true,
  value: vi.fn().mockResolvedValue(undefined),
});
Object.defineProperty(HTMLMediaElement.prototype, "pause", {
  configurable: true,
  value: vi.fn(),
});

Object.defineProperty(HTMLElement.prototype, "setPointerCapture", {
  configurable: true,
  value: vi.fn(),
});

class ResizeObserverMock {constructor(private cb:ResizeObserverCallback){} observe(target:Element){this.cb([{target,contentRect:{width:900,height:400}} as unknown as ResizeObserverEntry],this as unknown as ResizeObserver)} unobserve(){} disconnect(){}}
vi.stubGlobal('ResizeObserver',ResizeObserverMock);
Object.defineProperty(HTMLCanvasElement.prototype,'getContext',{configurable:true,value:()=>({scale(){},translate(){},strokeText(){},fillText(){},save(){},beginPath(){},rect(){},clip(){},restore(){},fillRect(){},arc(){},fill(){},stroke(){}})});
