const {test} = require('node:test');
const assert = require('node:assert/strict');
const {advance, createAnimator} = require('../solar_model/assets/fan_animation.js');

function rig() {
    let next = 0, hidden = false, reduced = false, mounted = true;
    const pending = new Map(), paints = [];
    const animator = createAnimator({
        request(fn) { pending.set(++next, fn); return next; },
        cancel(id) { pending.delete(id); }, hidden: () => hidden,
        reduced: () => reduced, mounted: () => mounted,
        paint(pose, angle, frames) { paints.push({pose, angle, frames}); }
    });
    return {animator, pending, paints,
        frame(now) {
            const callbacks = [...pending.values()]; pending.clear();
            callbacks.forEach(fn => fn(now));
        },
        command(rpm = 12) { animator.configure({centre: [3.6, -.5, 1.31], visual_rpm: rpm, session: 'test'}); },
        hidden(value) { hidden = value; animator.refresh(); },
        reduced(value) { reduced = value; animator.refresh(); },
        unmount() { mounted = false; }
    };
}

test('native rigid rotation preserves fan centre and leaves geometry untouched', () => {
    const r = rig(); r.command(); r.frame(0); r.frame(20);
    const pose = r.paints.at(-1).pose;
    assert.deepEqual(pose.origin, [3.6, -.5, 1.31]);
    assert.deepEqual(pose.position, [0, 0, 0]);
    assert.deepEqual(pose.orientation.slice(1), [0, 0]);
    assert.ok(pose.orientation[0] > 0);
    assert.equal(pose.useBounds, false);
    assert.equal(pose.visibility, true);
    assert.ok(!('points' in pose) && !('children' in pose));
});

test('elapsed-time integration gives equal phase at different display refresh rates', () => {
    const phases = [30, 60, 144].map(hz => {
        const state = {angle: 0, speed: 0};
        for (let i = 0; i < hz * 3; i++) advance(state, 12 * 2 * Math.PI / 60, 1 / hz);
        return state;
    });
    for (const state of phases) {
        assert.ok(Math.abs(state.angle - phases[0].angle) < 1e-12);
        assert.ok(Math.abs(state.speed - phases[0].speed) < 1e-12);
    }
});

test('one local frame loop, even with repeated cooling commands', () => {
    const r = rig(); r.command();
    for (let i = 0; i < 100; i++) r.command();
    assert.equal(r.pending.size, 1);
    for (let i = 0; i < 121; i++) r.frame(i * 1000 / 60);
    assert.equal(r.paints.length, 121);
    assert.equal(r.pending.size, 1);
    const speed = r.animator.snapshot().speed;
    r.command(); r.frame(2020);
    assert.ok(r.animator.snapshot().speed >= speed); // demand update does not reset phase
    assert.equal(r.pending.size, 1);
});

test('smooth start and coast-down stop without scheduling idle frames', () => {
    const r = rig(); r.command(); r.frame(0); r.frame(20);
    const starting = r.animator.snapshot();
    assert.ok(starting.speed > 0 && starting.speed < 12 * 2 * Math.PI / 60);
    for (let i = 2; i <= 150; i++) r.frame(i * 20);
    const running = r.animator.snapshot();
    r.command(0); r.frame(3020);
    assert.ok(r.animator.snapshot().speed < running.speed);
    assert.ok(r.animator.snapshot().speed > 0);
    for (let i = 152; i < 450; i++) r.frame(i * 20);
    assert.equal(r.animator.snapshot().speed, 0);
    assert.equal(r.pending.size, 0);
    const finalAngle = r.animator.snapshot().angle;
    r.command(0); r.frame(20000);
    assert.equal(r.animator.snapshot().angle, finalAngle);
});

test('hidden/offscreen/reduced-motion tabs pause and resume without jumps', () => {
    const r = rig(); r.command(); r.frame(0); r.frame(20);
    for (const change of [v => r.hidden(v), v => r.animator.visibility(!v), v => r.reduced(v)]) {
        change(true); assert.equal(r.pending.size, 0);
        const phase = r.animator.snapshot().angle;
        change(false); assert.equal(r.pending.size, 1);
        r.frame(1000000);
        assert.equal(r.animator.snapshot().angle, phase);
    }
    r.unmount(); r.frame(1000020);
    assert.equal(r.pending.size, 0);
    r.animator.dispose(); r.command();
    assert.equal(r.pending.size, 0);
});

test('high-refresh displays cap updates; long stalls cannot jump the rotor', () => {
    const r = rig(); r.command();
    for (let i = 0; i < 241; i++) r.frame(i * 1000 / 120);
    assert.ok(r.paints.length >= 119 && r.paints.length <= 122);
    const phase = r.animator.snapshot().angle;
    r.frame(60000);
    assert.ok(r.animator.snapshot().angle - phase <= 12 * 2 * Math.PI / 60 * .05 + 1e-12);
});
