package inference

import (
	"context"
	"errors"
	"sync/atomic"
	"time"
)

// ErrBusy means the queue is full or the wait for a slot ran out.
var ErrBusy = errors.New("inference queue busy")

// Queue lets `concurrency` inferences run while at most `depth` more wait.
// One Mac serves everyone, so this is deliberately small (docs/API_CONTRACT.md).
type Queue struct {
	slots   chan struct{}
	waiting atomic.Int32
	depth   int32
}

func NewQueue(concurrency, depth int) *Queue {
	return &Queue{slots: make(chan struct{}, concurrency), depth: int32(depth)}
}

// Acquire returns a release func, ErrBusy, or the context's error.
func (q *Queue) Acquire(ctx context.Context, maxWait time.Duration) (func(), error) {
	select {
	case q.slots <- struct{}{}:
		return q.release, nil
	default:
	}
	if q.waiting.Add(1) > q.depth {
		q.waiting.Add(-1)
		return nil, ErrBusy
	}
	defer q.waiting.Add(-1)
	timer := time.NewTimer(maxWait)
	defer timer.Stop()
	select {
	case q.slots <- struct{}{}:
		return q.release, nil
	case <-timer.C:
		return nil, ErrBusy
	case <-ctx.Done():
		return nil, ctx.Err()
	}
}

func (q *Queue) release() { <-q.slots }

// Waiting is the number of requests currently queued (for tests and metrics).
func (q *Queue) Waiting() int { return int(q.waiting.Load()) }
